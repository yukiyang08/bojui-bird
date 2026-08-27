import re

POINT_RE = re.compile(r"^([+-]\d+)(?:\s+|$)")

BOT_MEMBER_ID = "BOT"


def extract_mention(text: str, message: dict) -> tuple[str, str, str] | None:
    """Pulls (user_id, display_name, text_with_mention_removed) from a LINE
    mention payload. Index/length are offsets into `text`."""
    mentionees = (message.get("mention") or {}).get("mentionees", [])
    if not mentionees:
        return None
    m = mentionees[0]
    user_id = m.get("userId")
    if not user_id:
        return None
    idx, length = m["index"], m["length"]
    display_name = text[idx : idx + length]
    remaining = (text[:idx] + text[idx + length :]).strip()
    return user_id, display_name, remaining


def without_first_mention(text: str, message: dict) -> str | None:
    """`text` with the first @mention's span sliced out and trimmed, so a
    mention-first message like `@小明 +1 遲到` becomes `+1 遲到`. None when there
    is no usable mention."""
    mentionees = (message.get("mention") or {}).get("mentionees", [])
    if not mentionees:
        return None
    m = mentionees[0]
    idx, length = m.get("index"), m.get("length")
    if idx is None or length is None:
        return None
    return (text[:idx] + text[idx + length :]).strip()


def mention_targets_self(message: dict) -> bool:
    """True when the first mention points at the bot itself — LINE flags that
    mentionee with `isSelf` (and often omits its userId)."""
    mentionees = (message.get("mention") or {}).get("mentionees", [])
    return bool(mentionees) and bool(mentionees[0].get("isSelf"))


def parse_point_delta(text: str) -> int | None:
    m = POINT_RE.match(text)
    return int(m.group(1)) if m else None


def extract_reason(remaining: str, delta: int) -> str:
    token = f"+{delta}" if delta > 0 else str(delta)
    if remaining.startswith(token):
        remaining = remaining[len(token) :]
    return remaining.strip()


def parse_settlement_command(text: str) -> tuple[str, int | None]:
    """`!算帳 續攤火鍋 11880` -> ("續攤火鍋", 11880); `!算帳 11880` -> ("聚餐", 11880);
    `!算帳 火鍋` -> ("火鍋", None); `!算帳` -> ("聚餐", None). A `None` amount means
    "use the group's dinner target"."""
    tokens = text[len("!算帳") :].strip().split()
    if not tokens:
        return "聚餐", None
    if tokens[-1].isdigit():
        return " ".join(tokens[:-1]) or "聚餐", int(tokens[-1])
    return " ".join(tokens) or "聚餐", None


def parse_target_command(text: str) -> int | None:
    """`!目標 12000` -> 12000; `!目標` (or anything non-numeric) -> None, meaning
    "just show the current target"."""
    tokens = text[len("!目標") :].strip().split()
    return int(tokens[0]) if tokens and tokens[0].isdigit() else None


def clean_target(amount: int) -> int:
    if amount <= 0:
        raise ValueError("目標金額要大於 0")
    return int(amount)


def calc_settlement(points: list[int], amount: int) -> list[int]:
    """Split `amount` by score: each person's share is weighted by how far their
    score sits below the top score, so the highest scorer pays the smallest share
    and the lowest scorer the largest. Every weight is >= 1, so no one is ever
    pushed to a negative payment ("refund"), and the shares always sum to
    `amount`. Everyone tied -> even split."""
    n = len(points)
    if n == 0:
        return []
    top = max(points)
    weights = [(top - p) + 1 for p in points]
    total_w = sum(weights)
    pays = [round(amount * w / total_w) for w in weights]
    # absorb rounding drift on the current largest payer — big enough to stay >= 0
    biggest = max(range(n), key=lambda k: pays[k])
    pays[biggest] += amount - sum(pays)
    return pays


def leaderboard_data(members: list[dict]) -> dict:
    by_points_desc = sorted(members, key=lambda m: m["total_points"], reverse=True)
    keep = lambda ms: [{"display_name": m["display_name"], "total_points": m["total_points"]} for m in ms]
    return {"merit": keep(by_points_desc[:5]), "sinner": keep(list(reversed(by_points_desc))[:5])}


def build_liff_payload(
    members: list[dict],
    records: list[dict],
    dinner_target: int | None = None,
    log_size: int = 20,
) -> dict:
    """LIFF page shape: one overall ranking (highest score first, i.e. most merit
    on top) where each row also carries `pay` — what that person would owe for
    the dinner right now at the current target and points (None if no target) —
    separate recent-activity feeds for good and bad deeds, the group's dinner
    target, and a member list for the "add a record" picker. `records` is
    expected newest-first. Each log entry carries `id` so the page can edit,
    delete, or add alongside it."""
    ranked = sorted(members, key=lambda m: m["total_points"], reverse=True)
    payers = [m for m in ranked if m.get("line_user_id") != BOT_MEMBER_ID]
    pay_by_id = {}
    if dinner_target and payers:
        amounts = calc_settlement([m["total_points"] for m in payers], dinner_target)
        pay_by_id = {m["line_user_id"]: a for m, a in zip(payers, amounts)}
    ranking = [
        {
            "display_name": m["display_name"],
            "total_points": m["total_points"],
            "pay": pay_by_id.get(m.get("line_user_id")),
        }
        for m in ranked
    ]
    names = {m["line_user_id"]: m["display_name"] for m in members}
    entry = lambda r: {
        "id": r.get("id"),
        "display_name": names.get(r["target_user_id"], "?"),
        "delta": r["delta"],
        "reason": r.get("reason") or "",
        "created_at": r.get("created_at"),
    }
    merit_log = [entry(r) for r in records if r["delta"] > 0][:log_size]
    sin_log = [entry(r) for r in records if r["delta"] < 0][:log_size]
    member_list = sorted(
        (
            {"line_user_id": m["line_user_id"], "display_name": m["display_name"]}
            for m in members
            if m["line_user_id"] != BOT_MEMBER_ID
        ),
        key=lambda m: m["display_name"] or "",
    )
    return {
        "ranking": ranking,
        "merit_log": merit_log,
        "sin_log": sin_log,
        "dinner_target": dinner_target,
        "members": member_list,
    }


def clean_record_edit(delta, reason) -> dict:
    """Validate an edit from the LIFF page and return only the point_records
    columns to update. `None` means 'leave this field alone'."""
    update: dict = {}
    if delta is not None:
        d = int(delta)
        if d == 0:
            raise ValueError("點數不能是 0")
        update["delta"] = d
    if reason is not None:
        update["reason"] = reason.strip() or None
    return update


def format_leaderboard_text(members: list[dict]) -> str:
    if not members:
        return "還沒有任何記點紀錄"
    ranked = sorted(members, key=lambda m: m["total_points"], reverse=True)
    lines = ["戰績排行"]
    for i, m in enumerate(ranked):
        p = m["total_points"]
        lines.append(f"{i + 1}. {m['display_name']} {'+' if p > 0 else ''}{p}")
    return "\n".join(lines)


def format_history_text(display_name: str, records: list[dict]) -> str:
    if not records:
        return f"{display_name} 還沒有任何紀錄"
    lines = [f"{display_name} 最近紀錄"]
    for r in records:
        sign = "+" if r["delta"] > 0 else ""
        reason = f"（{r['reason']}）" if r.get("reason") else ""
        lines.append(f"{sign}{r['delta']} {reason}")
    return "\n".join(lines)


def format_settlement_text(title: str, members: list[dict], amount: int | None) -> str:
    if amount is None:
        return "還沒設定大餐目標金額，用 `!目標 12000` 設定，或 `!算帳 12000` 直接給金額"
    members = [m for m in members if m.get("line_user_id") != BOT_MEMBER_ID]
    if not members:
        return "還沒有人有記點紀錄，無法算帳"
    ranked = sorted(members, key=lambda m: m["total_points"], reverse=True)
    payments = calc_settlement([m["total_points"] for m in ranked], amount)
    lines = [f"{title}｜總金額 {amount} 元，共 {len(ranked)} 人"]
    for m, pay in zip(ranked, payments):
        lines.append(f"{m['display_name']}（{m['total_points']:+d}）：{pay} 元")
    return "\n".join(lines)


def format_target_text(amount: int | None) -> str:
    if amount is None:
        return "目前沒有設定大餐目標金額，用 `!目標 12000` 設定"
    return f"大餐目標金額：{amount} 元（`!算帳` 不帶數字就用這個金額）"


def chat_history_turns(rows: list[dict]) -> list[tuple[str, str]]:
    """DB rows (newest-first, each a {"role", "text"} dict) -> oldest-first
    (role, text) tuples in the shape the Gemini SDK wants for `contents`."""
    return [(r["role"], r["text"]) for r in reversed(rows)]
