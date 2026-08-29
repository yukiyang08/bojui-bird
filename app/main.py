import logging
import os

from dotenv import load_dotenv

load_dotenv()

if os.environ.get("GCP_SA_JSON"):
    import pathlib

    _sa = pathlib.Path("/tmp/gcp-sa.json")
    _sa.write_text(os.environ["GCP_SA_JSON"])
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_sa)

log = logging.getLogger("uvicorn.error")

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
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

# 前後端分開部署時（例如前端放 Vercel），把前端網址填進 ALLOWED_ORIGINS
# （逗號分隔）。同源部署可留空。
_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.mount("/liff", StaticFiles(directory="static", html=True), name="liff")


@app.get("/")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config")
async def config() -> dict:
    return {"liffId": os.environ.get("LIFF_ID", "")}


@app.post("/api/debug")
async def debug(payload: dict = Body(...)) -> dict:
    log.info("LIFF debug: %s", payload)
    return {"ok": True}


def _guard(fn, *args, **kwargs) -> dict:
    """Run a command, turning a DB/library exception into a readable 500 (so the
    LIFF shows the real reason, e.g. a missing column) and a `{ok: False}` result
    into a 400."""
    try:
        result = fn(*args, **kwargs)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — surface anything the DB layer throws
        log.exception("%s failed", fn.__name__)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    if isinstance(result, dict) and result.get("ok") is False:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/leaderboard/{line_group_id}")
async def api_leaderboard(line_group_id: str) -> dict:
    # ponytail: no auth check — line_group_id is an unguessable LINE group id,
    # only reachable by opening the LIFF page from inside that group's chat.
    log.info("leaderboard: group=%s", line_group_id)
    return _guard(leaderboard_payload, get_client(), line_group_id)


@app.post("/api/records")
async def api_add_record(payload: dict = Body(...)) -> dict:
    return _guard(
        add_record,
        get_client(),
        payload.get("line_group_id", ""),
        payload.get("target_user_id", ""),
        delta=payload.get("delta"),
        reason=payload.get("reason"),
    )


@app.put("/api/target")
async def api_set_target(payload: dict = Body(...)) -> dict:
    return _guard(
        set_dinner_target, get_client(), payload.get("line_group_id", ""), payload.get("amount")
    )


@app.patch("/api/records/{record_id}")
async def api_edit_record(record_id: str, payload: dict = Body(...)) -> dict:
    # ponytail: same no-auth trust model as api_leaderboard — the record id is
    # only handed out by that group-scoped endpoint.
    return _guard(
        edit_record, get_client(), record_id, delta=payload.get("delta"), reason=payload.get("reason")
    )


@app.delete("/api/records/{record_id}")
async def api_delete_record(record_id: str) -> dict:
    return _guard(delete_record, get_client(), record_id)


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
        src = event.get("source", {})
        log.info(
            "event: source=%s group=%s text=%r",
            src.get("type"),
            src.get("groupId"),
            event["message"].get("text"),
        )
        reply_text = handle_message(client, event)
        log.info("reply: %r", reply_text)
        if reply_text:
            await reply_message(event["replyToken"], reply_text)
    return {"status": "ok"}
