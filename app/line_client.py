import base64
import hashlib
import hmac
import logging
import os

import httpx

log = logging.getLogger("uvicorn.error")


def verify_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    mac = hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode()
    return hmac.compare_digest(expected, signature)


async def reply_message(reply_token: str, text: str) -> None:
    token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={"Authorization": f"Bearer {token}"},
            json={"replyToken": reply_token, "messages": [{"type": "text", "text": text}]},
        )
    if res.status_code != 200:
        log.error("LINE reply failed: %s %s", res.status_code, res.text)
