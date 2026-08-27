import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles

from app.commands import (
    add_record,
    delete_record,
    edit_record,
    handle_message,
    leaderboard_payload,
    set_dinner_target,
)
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


@app.post("/api/records")
async def api_add_record(payload: dict = Body(...)) -> dict:
    result = add_record(
        get_client(),
        payload.get("line_group_id", ""),
        payload.get("target_user_id", ""),
        delta=payload.get("delta"),
        reason=payload.get("reason"),
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.put("/api/target")
async def api_set_target(payload: dict = Body(...)) -> dict:
    result = set_dinner_target(get_client(), payload.get("line_group_id", ""), payload.get("amount"))
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.patch("/api/records/{record_id}")
async def api_edit_record(record_id: str, payload: dict = Body(...)) -> dict:
    # ponytail: same no-auth trust model as api_leaderboard — the record id is
    # only handed out by that group-scoped endpoint.
    result = edit_record(
        get_client(), record_id, delta=payload.get("delta"), reason=payload.get("reason")
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.delete("/api/records/{record_id}")
async def api_delete_record(record_id: str) -> dict:
    result = delete_record(get_client(), record_id)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


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
