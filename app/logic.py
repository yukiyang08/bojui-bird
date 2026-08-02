import re

POINT_RE = re.compile(r"^([+-]\d+)\s+")


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


def parse_point_delta(text: str) -> int | None:
    m = POINT_RE.match(text)
    return int(m.group(1)) if m else None


def extract_reason(remaining: str, delta: int) -> str:
    token = f"+{delta}" if delta > 0 else str(delta)
    if remaining.startswith(token):
        remaining = remaining[len(token) :]
    return remaining.strip()


def parse_settlement_command(text: str) -> tuple[str, int] | None:
    """`!算帳 續攤火鍋 11880` -> ("續攤火鍋", 11880); `!算帳 11880` -> ("聚餐", 11880)."""
    remainder = text[len("!算帳") :].strip()
    if not remainder:
        return None
    tokens = remainder.split()
    amount_str = tokens[-1]
    if not amount_str.isdigit():
        return None
    title = " ".join(tokens[:-1]) or "聚餐"
    return title, int(amount_str)


def calc_settlement(points: list[int], amount: int, point_value: int) -> list[int]:
    """Even split, then shifted by each person's points, then the rounding
    remainder is dumped onto the last person so the total matches exactly."""
    n = len(points)
    if n == 0:
        return []
    base = amount / n
    rounded = [round(base + p * point_value) for p in points]
    rounded[-1] += amount - sum(rounded)  # ponytail: last member absorbs rounding, fine for small groups
    return rounded


def leaderboard_data(members: list[dict]) -> dict:
    sorted_members = sorted(members, key=lambda m: m["total_points"])
    keep = lambda ms: [{"display_name": m["display_name"], "total_points": m["total_points"]} for m in ms]
    return {"merit": keep(sorted_members[:5]), "sinner": keep(list(reversed(sorted_members))[:5])}


def format_leaderboard_text(members: list[dict]) -> str:
    if not members:
        return "還沒有任何記點紀錄"
    data = leaderboard_data(members)
    lines = ["功德榜（點數最低）"]
    lines += [f"{i + 1}. {m['display_name']} {m['total_points']} 點" for i, m in enumerate(data["merit"])]
    lines.append("")
    lines.append("罪人榜（點數最高）")
    lines += [f"{i + 1}. {m['display_name']} {m['total_points']} 點" for i, m in enumerate(data["sinner"])]
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


def format_settlement_text(title: str, members: list[dict], amount: int, point_value: int) -> str:
    if not members:
        return "還沒有人有記點紀錄，無法算帳"
    payments = calc_settlement([m["total_points"] for m in members], amount, point_value)
    lines = [f"{title}｜總金額 {amount} 元，共 {len(members)} 人"]
    for m, pay in zip(members, payments):
        lines.append(f"{m['display_name']}：{pay} 元")
    return "\n".join(lines)
