import os
import re
import random
import difflib
import unicodedata
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

PLAYERS_FILE = os.path.join(os.path.dirname(__file__), "players.json")

app = FastAPI()


def load_players() -> dict:
    import json
    with open(PLAYERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_players(data: dict):
    import json
    with open(PLAYERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


players = load_players()

BLACKLISTS = [
    ["חבר", "ציפס"],
]


def check_blacklist(player, team, blacklists):
    for blacklist in blacklists:
        if player in blacklist:
            for black_player in blacklist:
                if black_player in team:
                    return False
    return True


def generate_teams(selected_players: list[str]):
    random_multiplier = random.uniform(0.95, 1.2)
    randomized = {
        p: (players[p] + random.uniform(0, 0.5)) * random_multiplier
        for p in selected_players
        if p in players
    }
    sorted_players = sorted(randomized.items(), key=lambda x: x[1], reverse=True)

    teams = [[], [], []]
    sums = [0.0, 0.0, 0.0]

    for player, score in sorted_players:
        placed = False
        # Try teams in order of current lowest sum
        order = sorted(range(3), key=lambda i: sums[i])
        for i in order:
            if len(teams[i]) < 5 and check_blacklist(player, teams[i], BLACKLISTS):
                teams[i].append(player)
                sums[i] += score
                placed = True
                break
        if not placed:
            # Force place ignoring blacklist if no valid slot found
            for i in order:
                if len(teams[i]) < 5:
                    teams[i].append(player)
                    sums[i] += score
                    break

    return [
        {"players": teams[i], "score": round(sum(players[p] for p in teams[i]), 1)}
        for i in range(3)
    ]


class TeamsRequest(BaseModel):
    players: list[str]


class AddPlayerRequest(BaseModel):
    password: str
    name: str
    score: float


@app.get("/api/players")
def get_players():
    return sorted(players.keys(), key=lambda p: players[p], reverse=True)


@app.post("/api/players/add")
def add_player(req: AddPlayerRequest):
    if req.password != ADMIN_PASSWORD:
        return {"error": "סיסמה שגויה"}
    name = req.name.strip()
    if not name:
        return {"error": "שם לא יכול להיות ריק"}
    if name in players:
        return {"error": f"{name} כבר קיים במאגר עם ציון {players[name]}"}
    if not (0 < req.score <= 20):
        return {"error": "ציון חייב להיות בין 0 ל-20"}
    players[name] = req.score
    save_players(players)
    return {"ok": True, "name": name, "score": req.score}


@app.post("/api/teams")
def create_teams(req: TeamsRequest):
    if len(req.players) != 15:
        return {"error": f"Select exactly 15 players (got {len(req.players)})"}
    return {"teams": generate_teams(req.players)}


def clean_name(raw: str) -> str:
    raw = re.sub(r"\s*@\S+.*$", "", raw)                        # strip @mention and anything after
    raw = "".join(c for c in raw if unicodedata.category(c) != "Cf")  # strip invisible chars
    raw = re.sub(r"[a-zA-Z0-9]+\s*$", "", raw)                 # strip trailing Latin/digits
    return raw.strip()


def resolve_player(name: str) -> str | None:
    if name in players:
        return name
    matches = difflib.get_close_matches(name, players.keys(), n=1, cutoff=0.75)
    return matches[0] if matches else None


def parse_players_message(text: str) -> tuple[list[str], list[str]]:
    found, unknown = [], []
    for line in text.split("\n"):
        match = re.match(r"^\d+\.\s*(.*)", line)
        if not match:
            continue
        name = clean_name(match.group(1))
        if not name:
            continue
        resolved = resolve_player(name)
        if resolved:
            found.append(resolved)
        else:
            unknown.append(name)
    return found, unknown


async def send_message(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text})


@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()
    message = update.get("message") or update.get("edited_message", {})
    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id")

    if not chat_id or not text:
        return {"ok": True}

    found, unknown = parse_players_message(text)

    if unknown:
        names = ", ".join(unknown)
        await send_message(chat_id, f"⚠️ השחקנים הבאים לא נמצאו במאגר:\n{names}\n\nבדוק את השמות ונסה שוב.")
        return {"ok": True}

    if len(found) != 15:
        await send_message(chat_id, f"נמצאו {len(found)} שחקנים — נדרשים בדיוק 15.")
        return {"ok": True}

    teams = generate_teams(found)
    labels = ["קבוצה א", "קבוצה ב", "קבוצה ג"]
    lines = []
    for i, team in enumerate(teams):
        lines.append(f"⚽ {labels[i]} (סה\"כ: {team['score']})")
        for p in team["players"]:
            lines.append(f"  • {p}")
        lines.append("")

    await send_message(chat_id, "\n".join(lines).strip())
    return {"ok": True}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
