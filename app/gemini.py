"""不揪鳥的閒聊層。只有「@不揪鳥 + 不是既有指令」時才會呼叫，純聊天＋Google 搜尋，
不記點、不改資料。

多把 key（GEMINI_API_KEYS）＋多個模型（_MODELS，寫在這支檔案裡）：會照「每個模型試完
所有 key、再換下一個模型」的順序輪，某組配額爆掉（429/quota）就記住位置、下次跳過往後試；
某個模型整個叫不動（404）就這輪之後都不再試它。全部失敗回 None，呼叫端退回一般說明。"""

import logging
import os
import re

log = logging.getLogger("uvicorn.error")


def _clean(text: str) -> str:
    """LINE 只顯示純文字，把 Markdown 記號拿掉：星號、反引號、標題井號、條列符號。"""
    t = (text or "").strip()
    t = t.replace("*", "").replace("`", "")
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)   # # 標題
    t = re.sub(r"^\s*[-–—•]\s+", "", t, flags=re.M)        # - 條列
    lines = [ln.strip() for ln in t.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    while lines and not lines[0]:
        lines.pop(0)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

try:
    from google import genai
    from google.genai import types
except ImportError:  # 套件沒裝也不要讓整個 app 掛掉
    genai = None
    types = None

# 依優先順序試，某個爆配額或叫不動（404）就換下一個。輕量／配額寬的排前面，
# pro 放最後墊底。叫不動的會自動被跳過，所以多列一些沒差。
_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-2.5-flash",
    "gemini-flash-latest",
]

_SYSTEM = (
    "你是「不揪鳥」，一個 LINE 群組的吉祥物，會認真回答群組成員的問題、聊天、或幫忙查詢新的資訊。"
    "你的性格幽默可愛、偶爾喜歡吐槽，口頭禪是不揪、啾咪，但這只是偶爾的調味，"
    "大部分回覆不需要用到，不要每句都講、也不要硬塞，看情境自然帶到就好。"
    "不談政治、宗教、成人內容。\n"
    "需要即時或不確定的資訊（店家、時間、新聞、路線等）就用 Google 搜尋查證，"
    "有查到相關網址就把網址直接貼在回覆裡（純文字即可，LINE 會自動變連結）。"
    "查不到就老實說不知道，不要編造網址、不要編造謊言。\n"
    "回覆用繁體中文、口語，直接講白話，不要用任何 Markdown 格式：不要星號、不要粗體。"
)

_keys_cache = None
_clients = {}       # key -> genai.Client
_bad_models = set()  # 這次執行期間確認叫不動的（404 / 不支援），之後跳過
_start = 0          # 下次從第幾組 (model, key) 開始試


def _keys() -> list[str]:
    """GEMINI_API_KEYS（逗號或換行分隔）可填多把；也接受單數的 GEMINI_API_KEY。"""
    global _keys_cache
    if _keys_cache is None:
        raw = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
        _keys_cache = [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]
    return _keys_cache


def _models() -> list[str]:
    return [m for m in _MODELS if m not in _bad_models] or _MODELS


def _client_for(key: str):
    c = _clients.get(key)
    if c is None:
        c = genai.Client(api_key=key)
        _clients[key] = c
    return c


def _looks_exhausted(err: Exception) -> bool:
    s = str(err).lower()
    return any(x in s for x in ("resource_exhausted", "429", "quota", "rate limit"))


def _model_gone(err: Exception) -> bool:
    s = str(err).lower()
    return any(x in s for x in ("not_found", "404", "not supported", "no longer available"))


def chat(user_text: str) -> str | None:
    global _start
    if genai is None or not user_text.strip():
        return None
    keys = _keys()
    if not keys:
        return None

    prompt = f"群組裡有人 @ 你，說：{user_text}\n\n用不揪鳥的口氣回一句話。"
    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM,
        max_output_tokens=2048,  # 有些型號會用掉一部分做內部思考，留寬一點
        temperature=0.8,
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )
    combos = [(m, k) for m in _models() for k in keys]  # 同一個 model 先試完所有 key，再換 model
    n = len(combos)
    base = _start
    for offset in range(n):
        i = (base + offset) % n
        model, key = combos[i]
        try:
            resp = _client_for(key).models.generate_content(model=model, contents=prompt, config=config)
            return _clean(resp.text or "") or None
        except Exception as e:  # noqa: BLE001
            if _model_gone(e):
                _bad_models.add(model)
                log.warning("gemini 模型 %s 叫不動，之後跳過：%s", model, e)
            elif _looks_exhausted(e):
                _start = (i + 1) % n  # 這組爆了，下次從下一組開始
                log.warning("gemini %s / key#%d 額度用完，換下一組", model, keys.index(key))
            else:
                log.warning("gemini %s / key#%d 失敗：%s", model, keys.index(key), e)
    return None
