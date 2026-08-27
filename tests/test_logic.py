import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

from app.logic import (
    BOT_MEMBER_ID,
    build_liff_payload,
    calc_settlement,
    chat_history_turns,
    clean_record_edit,
    clean_target,
    extract_mention,
    extract_reason,
    format_settlement_text,
    format_target_text,
    leaderboard_data,
    mention_targets_self,
    parse_point_delta,
    parse_settlement_command,
    parse_target_command,
    without_first_mention,
)


def test_extract_mention():
    text = "+1 @小明 遲到"
    message = {"mention": {"mentionees": [{"index": 3, "length": 3, "type": "user", "userId": "U123"}]}}
    user_id, display_name, remaining = extract_mention(text, message)
    assert user_id == "U123"
    assert display_name == "@小明"
    assert remaining == "+1  遲到"
    assert extract_mention("!排行榜", {}) is None


def test_mention_targets_self():
    assert mention_targets_self({"mention": {"mentionees": [{"index": 3, "length": 4, "isSelf": True}]}})
    assert not mention_targets_self({"mention": {"mentionees": [{"index": 3, "length": 3, "userId": "U1"}]}})
    assert not mention_targets_self({})


def test_parse_point_delta():
    assert parse_point_delta("+1 @小明 遲到") == 1
    assert parse_point_delta("-2 @老王 買手搖") == -2
    assert parse_point_delta("+1") == 1  # no reason, delta at end of string
    assert parse_point_delta("!排行榜") is None
    assert parse_point_delta("@小明 +1 遲到") is None  # mention-first: not at the head


def test_without_first_mention():
    # "@小明 +1 遲到" -> mention span [0,3) removed -> "+1 遲到"
    text = "@小明 +1 遲到"
    message = {"mention": {"mentionees": [{"index": 0, "length": 3, "userId": "U9"}]}}
    assert without_first_mention(text, message) == "+1 遲到"
    assert parse_point_delta(without_first_mention(text, message)) == 1
    assert without_first_mention("!排行榜", {}) is None


def test_extract_reason():
    assert extract_reason("+1  遲到", 1) == "遲到"
    assert extract_reason("-2  買手搖", -2) == "買手搖"


def test_parse_settlement_command():
    assert parse_settlement_command("!算帳 11880") == ("聚餐", 11880)
    assert parse_settlement_command("!算帳 續攤火鍋 11880") == ("續攤火鍋", 11880)
    assert parse_settlement_command("!算帳") == ("聚餐", None)  # fall back to dinner target
    assert parse_settlement_command("!算帳 火鍋") == ("火鍋", None)


def test_parse_target_command():
    assert parse_target_command("!目標 12000") == 12000
    assert parse_target_command("!目標") is None
    assert parse_target_command("!目標 貴") is None


def test_clean_target():
    assert clean_target(12000) == 12000
    with pytest.raises(ValueError):
        clean_target(0)
    with pytest.raises(ValueError):
        clean_target(-5)


def test_format_settlement_text_without_amount():
    assert "目標" in format_settlement_text("聚餐", [], None)


def test_format_target_text():
    assert format_target_text(None).startswith("目前沒有設定")
    assert "12000" in format_target_text(12000)


def test_calc_settlement_sums_to_total_and_never_negative():
    cases = [
        ([0, 0], 1000),
        ([1, -1], 1000),
        ([0, 0, 0], 1000),
        ([3, -2, 0, 1], 12345),
        ([20, -1, -1, -1], 9999),  # one huge saint, rest sinners
        ([-5, -5, 30], 7000),
    ]
    for points, amount in cases:
        result = calc_settlement(points, amount)
        assert sum(result) == amount, (points, amount, result)
        assert all(p >= 0 for p in result), (points, amount, result)  # no refunds


def test_calc_settlement_sinner_pays_more():
    # index 0 did a good deed (+1) -> pays less; index 1 messed up (-1) -> pays more
    result = calc_settlement([1, -1], 1000)
    assert result[1] > result[0]
    # everyone tied -> even split
    assert calc_settlement([2, 2, 2], 900) == [300, 300, 300]


def test_leaderboard_data():
    members = [{"display_name": f"人{i}", "total_points": i} for i in range(7)]
    data = leaderboard_data(members)
    assert [m["total_points"] for m in data["merit"]] == [6, 5, 4, 3, 2]
    assert [m["total_points"] for m in data["sinner"]] == [0, 1, 2, 3, 4]
    assert leaderboard_data([]) == {"merit": [], "sinner": []}


def test_build_liff_payload():
    members = [
        {"line_user_id": "U_ming", "display_name": "小明", "total_points": -3},
        {"line_user_id": "U_wang", "display_name": "老王", "total_points": 2},
        {"line_user_id": "U_ken", "display_name": "Ken", "total_points": 0},
    ]
    records = [  # newest first, as the DB query returns them
        {"id": "r1", "target_user_id": "U_wang", "delta": 2, "reason": "買手搖", "created_at": "2026-08-27T10:00:00Z"},
        {"id": "r2", "target_user_id": "U_ming", "delta": -1, "reason": "遲到", "created_at": "2026-08-27T09:00:00Z"},
        {"id": "r3", "target_user_id": "U_ming", "delta": -2, "reason": None, "created_at": "2026-08-26T09:00:00Z"},
    ]
    payload = build_liff_payload(members, records, dinner_target=8000)
    assert [m["total_points"] for m in payload["ranking"]] == [2, 0, -3]  # highest merit on top
    assert [e["display_name"] for e in payload["merit_log"]] == ["老王"]
    assert [e["delta"] for e in payload["sin_log"]] == [-1, -2]
    assert [e["id"] for e in payload["sin_log"]] == ["r2", "r3"]  # id carried through for editing
    assert payload["sin_log"][1]["reason"] == ""
    assert payload["dinner_target"] == 8000
    assert [m["display_name"] for m in payload["members"]] == ["Ken", "小明", "老王"]

    pays = [m["pay"] for m in payload["ranking"]]
    assert sum(pays) == 8000  # split still sums to the target exactly
    assert pays[0] < pays[-1]  # most merit pays least
    assert all(p >= 0 for p in pays)  # no refunds
    assert all(m["pay"] is None for m in build_liff_payload(members, records)["ranking"])  # no target -> no estimate


def test_bot_is_scored_but_never_pays():
    members = [
        {"line_user_id": "U_a", "display_name": "阿哲", "total_points": 3},
        {"line_user_id": "U_b", "display_name": "小明", "total_points": -3},
        {"line_user_id": BOT_MEMBER_ID, "display_name": "不揪鳥", "total_points": 5},
    ]
    payload = build_liff_payload(members, [], dinner_target=6000)
    by_name = {m["display_name"]: m for m in payload["ranking"]}
    assert by_name["不揪鳥"]["total_points"] == 5           # 上榜、有分數
    assert by_name["不揪鳥"]["pay"] is None                  # 但不分攤
    assert by_name["阿哲"]["pay"] + by_name["小明"]["pay"] == 6000  # 全額落在真人身上
    assert "不揪鳥" not in [m["display_name"] for m in payload["members"]]  # 記一筆選單不列它

    text = format_settlement_text("聚餐", members, 6000)
    assert "不揪鳥" not in text
    assert "共 2 人" in text


def test_clean_record_edit():
    assert clean_record_edit(None, None) == {}
    assert clean_record_edit(-3, "  遲到  ") == {"delta": -3, "reason": "遲到"}
    assert clean_record_edit(None, "   ") == {"reason": None}  # blank reason clears it
    assert clean_record_edit("2", None) == {"delta": 2}
    with pytest.raises(ValueError):
        clean_record_edit(0, None)


def test_chat_history_turns():
    rows = [  # newest-first, like the DB query returns
        {"role": "model", "text": "不揪不揪"},
        {"role": "user", "text": "你在幹嘛"},
    ]
    assert chat_history_turns(rows) == [("user", "你在幹嘛"), ("model", "不揪不揪")]
    assert chat_history_turns([]) == []


if __name__ == "__main__":
    test_extract_mention()
    test_mention_targets_self()
    test_parse_point_delta()
    test_without_first_mention()
    test_extract_reason()
    test_parse_settlement_command()
    test_parse_target_command()
    test_clean_target()
    test_format_settlement_text_without_amount()
    test_format_target_text()
    test_calc_settlement_sums_to_total_and_never_negative()
    test_calc_settlement_sinner_pays_more()
    test_leaderboard_data()
    test_build_liff_payload()
    test_bot_is_scored_but_never_pays()
    test_clean_record_edit()
    test_chat_history_turns()
    print("all tests passed")
