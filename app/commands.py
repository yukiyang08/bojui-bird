from app.logic import (
    build_liff_payload,
    clean_record_edit,
    clean_target,
    extract_mention,
    extract_reason,
    format_history_text,
    format_leaderboard_text,
    format_settlement_text,
    format_target_text,
    mention_targets_self,
    parse_point_delta,
    parse_settlement_command,
    parse_target_command,
    without_first_mention,
)

BOT_DECLINE = "我只負責記帳 不負責付錢喔 不揪不揪"

BOT_HELP = "\n".join(
    [
        "不揪不揪鳥 使用說明",
        "",
        "記點（記得 @ 對象，數字前後都行）",
        "　@小明 +1 買飲料　做好事，加分",
        "　@小明 -1 遲到　　做錯事，扣分",
        "　+1 @小明 買飲料　也可以（+/- 放最前面）",
        "",
        "排行榜",
        "　!排行榜　　　看功德榜 / 罪人榜",
        "　!查 @小明　　看某人最近紀錄",
        "",
        "聚餐算帳",
        "　!目標 12000　　設定大餐目標金額",
        "　!算帳　　　　　依分數分攤目標金額（分數高付少，沒人要退錢）",
        "　!算帳 火鍋 3000　直接給名稱和金額",
        "",
        "排行榜網頁可以編輯 / 手動新增紀錄、改目標金額",
    ]
)


# 群組的「大餐目標金額」存在 dinner_events 裡、用這個 title 標記的那一列（每組一列，
# 會被覆蓋更新）。實際的 !算帳 紀錄用聚餐名稱當 title，不會互相影響。
_TARGET_TITLE = "大餐目標"


def _read_dinner_target(client, group_id: str) -> int | None:
    res = (
        client.table("dinner_events")
        .select("total_amount")
        .eq("group_id", group_id)
        .eq("title", _TARGET_TITLE)
        .limit(1)
        .execute()
    )
    return res.data[0]["total_amount"] if res.data else None


def _write_dinner_target(client, group_id: str, amount: int) -> None:
    res = (
        client.table("dinner_events")
        .select("id")
        .eq("group_id", group_id)
        .eq("title", _TARGET_TITLE)
        .limit(1)
        .execute()
    )
    if res.data:
        client.table("dinner_events").update({"total_amount": amount}).eq("id", res.data[0]["id"]).execute()
    else:
        client.table("dinner_events").insert(
            {"group_id": group_id, "title": _TARGET_TITLE, "total_amount": amount}
        ).execute()


def get_or_create_group(client, line_group_id: str) -> dict:
    res = client.table("groups").select("*").eq("line_group_id", line_group_id).execute()
    if res.data:
        return res.data[0]
    res = client.table("groups").insert({"line_group_id": line_group_id}).execute()
    return res.data[0]


def get_or_create_member(client, group_id: str, line_user_id: str, display_name: str) -> dict:
    res = (
        client.table("group_members")
        .select("*")
        .eq("group_id", group_id)
        .eq("line_user_id", line_user_id)
        .execute()
    )
    if res.data:
        member = res.data[0]
        if display_name and member.get("display_name") != display_name:
            client.table("group_members").update({"display_name": display_name}).eq("id", member["id"]).execute()
            member["display_name"] = display_name
        return member
    res = client.table("group_members").insert(
        {"group_id": group_id, "line_user_id": line_user_id, "display_name": display_name, "total_points": 0}
    ).execute()
    return res.data[0]


def add_point(client, group: dict, recorder_user_id: str, delta: int, target_user_id: str, target_name: str, reason: str) -> str:
    member = get_or_create_member(client, group["id"], target_user_id, target_name)
    new_total = member["total_points"] + delta
    client.table("group_members").update({"total_points": new_total}).eq("id", member["id"]).execute()
    client.table("point_records").insert(
        {
            "group_id": group["id"],
            "target_user_id": target_user_id,
            "recorder_user_id": recorder_user_id,
            "delta": delta,
            "reason": reason or None,
        }
    ).execute()
    sign = "+" if delta > 0 else ""
    reason_part = f"（{reason}）" if reason else ""
    return f"{target_name} {sign}{delta} 點{reason_part}，目前 {new_total} 點"


def leaderboard(client, group: dict) -> str:
    res = client.table("group_members").select("*").eq("group_id", group["id"]).execute()
    return format_leaderboard_text(res.data)


def leaderboard_payload(client, line_group_id: str) -> dict:
    """Overall ranking + recent good/bad activity, JSON-shaped for the LIFF page."""
    group = get_or_create_group(client, line_group_id)
    members = client.table("group_members").select("*").eq("group_id", group["id"]).execute().data
    records = (
        client.table("point_records")
        .select("*")
        .eq("group_id", group["id"])
        .order("created_at", desc=True)
        .limit(50)
        .execute()
        .data
    )
    return build_liff_payload(members, records, _read_dinner_target(client, group["id"]))


def add_record(client, line_group_id: str, target_user_id: str, delta, reason=None) -> dict:
    """Manually add a record from the LIFF page. Only existing members can be a
    target (the page picks from the member list). ponytail: no auth, same trust
    model as the rest of the /api/* endpoints."""
    group = get_or_create_group(client, line_group_id)
    member = (
        client.table("group_members")
        .select("*")
        .eq("group_id", group["id"])
        .eq("line_user_id", target_user_id)
        .execute()
        .data
    )
    if not member:
        return {"ok": False, "error": "這個人不在群組名單裡"}
    if delta is None:
        return {"ok": False, "error": "要給點數"}
    try:
        clean = clean_record_edit(delta, reason)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    client.table("point_records").insert(
        {
            "group_id": group["id"],
            "target_user_id": target_user_id,
            "recorder_user_id": "liff",
            "delta": clean["delta"],
            "reason": clean.get("reason"),
        }
    ).execute()
    total = _recompute_member_total(client, group["id"], target_user_id)
    return {"ok": True, "total_points": total}


def set_dinner_target(client, line_group_id: str, amount) -> dict:
    group = get_or_create_group(client, line_group_id)
    try:
        value = clean_target(int(amount))
    except (ValueError, TypeError):
        return {"ok": False, "error": "目標金額要是大於 0 的數字"}
    _write_dinner_target(client, group["id"], value)
    return {"ok": True, "dinner_target": value}


def _recompute_member_total(client, group_id: str, target_user_id: str) -> int:
    """Rebuild a member's stored total from the sum of their point_records, so
    edits and deletes can't drift the running total."""
    rows = (
        client.table("point_records")
        .select("delta")
        .eq("group_id", group_id)
        .eq("target_user_id", target_user_id)
        .execute()
        .data
    )
    total = sum(r["delta"] for r in rows)
    client.table("group_members").update({"total_points": total}).eq("group_id", group_id).eq(
        "line_user_id", target_user_id
    ).execute()
    return total


def _fetch_record(client, record_id: str) -> dict | None:
    res = client.table("point_records").select("*").eq("id", record_id).execute()
    return res.data[0] if res.data else None


def edit_record(client, record_id: str, delta=None, reason=None) -> dict:
    """Update a past record's points and/or reason, then re-total the member.
    ponytail: no auth — same trust model as the read API (needs the record id,
    only obtainable via the group-scoped leaderboard endpoint)."""
    record = _fetch_record(client, record_id)
    if not record:
        return {"ok": False, "error": "找不到這筆紀錄"}
    try:
        update = clean_record_edit(delta, reason)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if update:
        client.table("point_records").update(update).eq("id", record_id).execute()
    total = _recompute_member_total(client, record["group_id"], record["target_user_id"])
    return {"ok": True, "total_points": total}


def delete_record(client, record_id: str) -> dict:
    record = _fetch_record(client, record_id)
    if not record:
        return {"ok": False, "error": "找不到這筆紀錄"}
    client.table("point_records").delete().eq("id", record_id).execute()
    total = _recompute_member_total(client, record["group_id"], record["target_user_id"])
    return {"ok": True, "total_points": total}


def history(client, group: dict, user_id: str, display_name: str) -> str:
    res = (
        client.table("point_records")
        .select("*")
        .eq("group_id", group["id"])
        .eq("target_user_id", user_id)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    return format_history_text(display_name, res.data)


def settlement(client, group: dict, title: str, amount: int | None) -> str:
    if amount is None:
        amount = _read_dinner_target(client, group["id"])
    if amount is None:
        return format_settlement_text(title, [], None)
    res = client.table("group_members").select("*").eq("group_id", group["id"]).execute()
    if title != _TARGET_TITLE:  # 別把這次算帳寫成目標列
        client.table("dinner_events").insert(
            {"group_id": group["id"], "title": title, "total_amount": amount}
        ).execute()
    return format_settlement_text(title, res.data, amount)


def target(client, group: dict, amount: int | None) -> str:
    if amount is None:
        return format_target_text(_read_dinner_target(client, group["id"]))
    try:
        value = clean_target(amount)
    except ValueError as e:
        return str(e)
    _write_dinner_target(client, group["id"], value)
    return format_target_text(value)


# 中文輸入法常打出全形標點／數字，統一成半形（一對一對應，不影響 mention 的 index）
_FULLWIDTH = str.maketrans("！＋－−０１２３４５６７８９＠", "!+--0123456789@")


def handle_message(client, event: dict) -> str | None:
    source = event["source"]
    if source.get("type") != "group":
        return None  # ponytail: PRD scope is group chats only

    message = event["message"]
    text = message["text"].translate(_FULLWIDTH).strip()
    group = get_or_create_group(client, source["groupId"])

    if text.startswith("!說明") or text.startswith("!help") or text.startswith("!使用說明"):
        return BOT_HELP

    if text.startswith("!排行榜"):
        return leaderboard(client, group)

    if text.startswith("!查"):
        mention = extract_mention(text, message)
        if not mention:
            return "請 @ 要查詢的人，例如：!查 @小明"
        user_id, display_name, _ = mention
        return history(client, group, user_id, display_name)

    if text.startswith("!目標"):
        return target(client, group, parse_target_command(text))

    if text.startswith("!算帳"):
        title, amount = parse_settlement_command(text)
        return settlement(client, group, title, amount)

    # 記點支援兩種寫法：「+1 @小明 遲到」(+/- 在前) 和「@小明 +1 遲到」(@ 在前)
    without = without_first_mention(text, message)
    delta = parse_point_delta(text)
    if delta is None and without is not None:
        delta = parse_point_delta(without)

    if mention_targets_self(message):
        return BOT_DECLINE if delta is not None else BOT_HELP

    if delta is not None:
        mention = extract_mention(text, message)
        if not mention:
            return "請 @ 對象，例如：@小明 -1 遲到 或 +1 @老王 買手搖"
        user_id, display_name, remaining = mention
        reason = extract_reason(remaining, delta)
        recorder_user_id = source.get("userId", "unknown")
        return add_point(client, group, recorder_user_id, delta, user_id, display_name, reason)

    return None
