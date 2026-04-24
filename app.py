import os
import re
import random
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = FastAPI()

players = {
    "רן": 17.5,
    "פלוס עידן": 17.5,
    "אהוד": 16,
    "אורי": 14,
    "איתי חבר של יותם": 15,
    "איתי גלוק": 15,
    "גלוק": 14.5,
    "דניאל חבר של יותם": 14,
    "פלוס אלון בלאס": 14,
    "יוני": 14.5,
    "עידן": 16,
    "גיא": 14.5,
    "כפיר": 14,
    "גנני": 13.5,
    "אלון פאר": 13.5,
    "לירן": 13.5,
    "אופק": 12.5,
    "נדב": 12,
    "הראל": 13.5,
    "אלעד מנור": 14.5,
    "לנדא": 13.5,
    "שקד": 13.5,
    "יניר": 13.5,
    "ניר": 13.5,
    "טוריאל": 14,
    "סגל": 14,
    "דין": 14,
    "ראם פדידה": 14,
    "אוריאל": 13.5,
    "חיות": 16,
    "מיכה": 15.5,
    "ראם שור": 16.5,
    "אריאל": 15.5,
    "גלעד": 12,
    "תומר האס": 16.5,
    "תומר רוזנפלד": 12,
    "גיל": 15.5,
    "עומר": 16.5,
    "מאור": 13.5,
    "מתן": 14,
    "אשכנזי": 15,
    "גוטהרץ": 12,
    "דניאל פלוס של גוטהרץ": 12,
    "פלוס של אריאל": 12,
    "שחק": 11.5,
    "אלון בלאס": 14,
    "פרבר": 15.5,
    "יותם": 15,
    "אלעד אליקים": 11,
    "דניאל": 11,
    "גיא הראל": 14,
    "עמית בר": 17,
    "עידו": 15,
    "רוי": 14.5,
    "חבר": 12.5,
    "יובל": 13.5,
    "טומי": 11.5,
    "סרנה": 13,
    "רון": 13.5,
    "איתמר": 14,
    "ציפס": 11.5,
    "איתמר ארז": 12.5,
    "טל": 15,
    "איטם": 15,
    "אלון אח של חבר": 13,
    "שטרן": 13,
    "רועי שטרן": 12.5,
    "אלירן": 12.5,
    "יהלי אזרחי": 14,
    "יהלי": 13,
    "חסדאי": 11.5,
    "שי": 11.5,
    "גור": 12.5,
    "מאור סולומון": 16.5,
    "יואב": 13.5,
    "אברגיל": 13.5,
    "ברזלי": 13,
    "פלוס אריאל אחד": 15.5,
    "פלוס אריאל שתיים": 14,
    "פלוס אריאל שלוש": 13,
    "פלוס אריאל ארבע": 13,
    "אביב": 16,
}

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


@app.get("/api/players")
def get_players():
    return sorted(players.keys(), key=lambda p: players[p], reverse=True)


@app.post("/api/teams")
def create_teams(req: TeamsRequest):
    if len(req.players) != 15:
        return {"error": f"Select exactly 15 players (got {len(req.players)})"}
    return {"teams": generate_teams(req.players)}


def parse_players_message(text: str) -> tuple[list[str], list[str]]:
    found, unknown = [], []
    for line in text.split("\n"):
        match = re.match(r"^\d+\.\s*(.*)", line)
        if not match:
            continue
        name = match.group(1)
        name = re.sub(r"@\S+", "", name)          # strip @mentions
        name = re.sub(r"[⁠‏‎]", "", name).strip()
        if not name:
            continue
        if name in players:
            found.append(name)
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
