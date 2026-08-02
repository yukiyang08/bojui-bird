import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles

from app.commands import handle_message, leaderboard_payload
from app.db import get_client
from app.line_client import reply_message, verify_signature

app = FastAPI()
app.mount("/liff", StaticFiles(directory="static", html=True), name="liff")


@app.get("/")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config")
async def config() -> dict:
    return {"liffId": os.environ.get("LIFF_ID", "")}


@app.get("/api/leaderboard/{line_group_id}")
async def api_leaderboard(line_group_id: str) -> dict:
    # ponytail: no auth check — line_group_id is an unguessable LINE group id,
    # only reachable by opening the LIFF page from inside that group's chat.
    # Add ID-token verification if the data becomes sensitive.
    return leaderboard_payload(get_client(), line_group_id)


@app.post("/callback")
async def callback(request: Request, x_line_signature: str = Header(alias="X-Line-Signature")) -> dict:
    body = await request.body()
    if not verify_signature(body, x_line_signature, os.environ["LINE_CHANNEL_SECRET"]):
        raise HTTPException(status_code=400, detail="invalid signature")

    payload = await request.json()
    client = get_client()
    for event in payload.get("events", []):
        if event.get("type") != "message" or event["message"].get("type") != "text":
            continue
        reply_text = handle_message(client, event)
        if reply_text:
            await reply_message(event["replyToken"], reply_text)
    return {"status": "ok"}
