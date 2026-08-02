from app.logic import (
    extract_mention,
    extract_reason,
    format_history_text,
    format_leaderboard_text,
    format_settlement_text,
    leaderboard_data,
    parse_point_delta,
    parse_settlement_command,
)


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
    """Same query as `leaderboard`, JSON-shaped for the LIFF page."""
    group = get_or_create_group(client, line_group_id)
    res = client.table("group_members").select("*").eq("group_id", group["id"]).execute()
    return leaderboard_data(res.data)


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


def settlement(client, group: dict, title: str, amount: int) -> str:
    res = client.table("group_members").select("*").eq("group_id", group["id"]).execute()
    client.table("dinner_events").insert(
        {"group_id": group["id"], "title": title, "total_amount": amount}
    ).execute()
    return format_settlement_text(title, res.data, amount, group.get("point_value_twd", 100))


def handle_message(client, event: dict) -> str | None:
    source = event["source"]
    if source.get("type") != "group":
        return None  # ponytail: PRD scope is group chats only

    message = event["message"]
    text = message["text"].strip()
    group = get_or_create_group(client, source["groupId"])

    if text.startswith("!排行榜"):
        return leaderboard(client, group)

    if text.startswith("!查"):
        mention = extract_mention(text, message)
        if not mention:
            return "請 @ 要查詢的人，例如：!查 @小明"
        user_id, display_name, _ = mention
        return history(client, group, user_id, display_name)

    if text.startswith("!算帳"):
        parsed = parse_settlement_command(text)
        if not parsed:
            return "格式：!算帳 [聚餐名稱] 金額，例如：!算帳 續攤火鍋 11880"
        title, amount = parsed
        return settlement(client, group, title, amount)

    delta = parse_point_delta(text)
    if delta is not None:
        mention = extract_mention(text, message)
        if not mention:
            return "請 @ 對象，例如：+1 @小明 遲到"
        user_id, display_name, remaining = mention
        reason = extract_reason(remaining, delta)
        recorder_user_id = source.get("userId", "unknown")
        return add_point(client, group, recorder_user_id, delta, user_id, display_name, reason)

    return None
