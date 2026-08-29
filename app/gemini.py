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
    """LINE 只顯示純文字，把 Markdown 記號跟偶爾冒出的 HTML 標籤拿掉。"""
    t = (text or "").strip()
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)  # 模型有時用 <br> 當換行
    t = re.sub(r"<[^>]+>", "", t)                   # 其他 HTML 標籤直接拔
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
    "gemini-flash-latest",        # 主力：閒聊、查資料都吃得下
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-flash-lite-latest",   # flash 全 429 時降級墊底
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]

_SYSTEM = (
    "你是「不揪鳥」，一個 LINE 群組的吉祥物，會認真回答群組成員的問題、聊天、或幫忙查詢新的資訊。"
    "你的性格幽默可愛、偶爾喜歡吐槽，有兩句口頭禪，用法不一樣：\n"
    "「不揪」意思是「沒有揪我」，是你（不揪鳥）自己在抱怨/吐槽沒被邀，只有在群組聊到聚餐、"
    "出遊、揪團之類、而你沒被算進去的時候，才用第一人稱撒嬌抱怨一句「不揪」，"
    "不是拿來形容別人或泛指揪團話題，跟這個情境無關就不要講。\n"
    "「啾咪」語感接近「愛你」「謝謝你」，是表達感謝、親暱、示好的語尾詞，"
    "只在真的有這種情緒（謝謝對方、覺得對方可愛、道別）時才用，不是隨口的語助詞，不要每句都講。\n"
    "兩句都是偶爾的調味，大部分回覆不需要用到任何一句。"
    "不談政治、宗教、成人內容。\n"
    "需要即時或不確定的資訊（店家、時間、新聞、路線等）就用 Google 搜尋查證，"
    "有查到相關網址就把網址直接貼在回覆裡（純文字即可，LINE 會自動變連結）。"
    "查不到就老實說不知道，不要編造網址、不要編造謊言。\n"
    "回覆用繁體中文、口語，直接講白話，不要用任何 Markdown 格式：不要星號、不要粗體。\n"
    "長度看情況：閒聊寒暄一兩句就好，要解釋或查資料就講清楚一點，別硬湊字也別敷衍。\n"
    "不用每次都喊對方名字或加稱呼語，直接回話就好，除非那句話本身在問「誰」之類需要點名。\n"
    "語氣平常心，像朋友在講話，不要每句都加驚嘆號"
)

_VERTEX = "vertex"  # combos 裡的佔位值，_client_for 認得
_VERTEX_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
_VERTEX_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global").strip()

_keys_cache = None
_clients = {}       # key -> genai.Client
_bad_models = set()  # 這次執行期間確認叫不動的（404 / 不支援），之後跳過


def _keys() -> list[str]:
    """GEMINI_API_KEYS（逗號或換行分隔）可填多把；也接受單數的 GEMINI_API_KEY。"""
    global _keys_cache
    if _keys_cache is None:
        raw = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
        ks = [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]
        if _VERTEX_PROJECT:
            ks.append(_VERTEX)  # 排最後：前面的 key 都爆了才輪到 Vertex
        _keys_cache = ks
    return _keys_cache


def _models() -> list[str]:
    return [m for m in _MODELS if m not in _bad_models] or _MODELS


def _client_for(key: str):
    c = _clients.get(key)
    if c is None:
        if key == _VERTEX:
            c = genai.Client(vertexai=True, project=_VERTEX_PROJECT, location=_VERTEX_LOCATION)
        else:
            c = genai.Client(api_key=key)
        _clients[key] = c
    return c


def _looks_exhausted(err: Exception) -> bool:
    s = str(err).lower()
    return any(x in s for x in ("resource_exhausted", "429", "quota", "rate limit"))


def _model_gone(err: Exception) -> bool:
    s = str(err).lower()
    return any(x in s for x in ("not_found", "404", "not supported", "no longer available"))


def chat(user_text: str, history: list[tuple[str, str]] | None = None) -> str | None:
    """`history`: 過去的對話，[(role, text), ...] 由舊到新，role 是 "user" 或 "model"。"""
    if genai is None or not user_text.strip():
        return None
    keys = _keys()
    if not keys:
        return None

    prompt = f"群組裡有人 @ 你，說：{user_text}\n\n用不揪鳥的口氣回覆。"
    contents = [types.Content(role=role, parts=[types.Part(text=text)]) for role, text in (history or [])]
    contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM,
        max_output_tokens=2048,
        temperature=0.8,
        tools=[types.Tool(google_search=types.GoogleSearch())],
        # 關掉內部思考：吉祥物閒聊用不到，還會偶爾把「google search / queries: ...」
        # 那種思考過程漏進回覆，順便省 token、變快。
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    # 同一個 model 先試完所有 key，再換 model。每次都從頭試（免費 key 的 RPM 額度會回復，
    # 不記位＝每通都先給免費的機會，真的還在爆才往後掉到 Vertex）。
    for model in _models():
        for key in keys:
            try:
                resp = _client_for(key).models.generate_content(model=model, contents=contents, config=config)
                return _clean(resp.text or "") or None
            except Exception as e:  # noqa: BLE001
                if _model_gone(e):
                    _bad_models.add(model)
                    log.warning("gemini 模型 %s 叫不動，之後跳過：%s", model, e)
                    break  # 這個 model 整個掛，換下一個
                lvl = "額度用完" if _looks_exhausted(e) else "失敗"
                log.warning("gemini %s / key#%d %s：%s", model, keys.index(key), lvl, e)
    return None
