import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.logic import (
    calc_settlement,
    extract_mention,
    extract_reason,
    leaderboard_data,
    parse_point_delta,
    parse_settlement_command,
)


def test_extract_mention():
    text = "+1 @小明 遲到"
    message = {"mention": {"mentionees": [{"index": 3, "length": 3, "type": "user", "userId": "U123"}]}}
    user_id, display_name, remaining = extract_mention(text, message)
    assert user_id == "U123"
    assert display_name == "@小明"
    assert remaining == "+1  遲到"
    assert extract_mention("!排行榜", {}) is None


def test_parse_point_delta():
    assert parse_point_delta("+1 @小明 遲到") == 1
    assert parse_point_delta("-2 @老王 買手搖") == -2
    assert parse_point_delta("!排行榜") is None


def test_extract_reason():
    assert extract_reason("+1  遲到", 1) == "遲到"
    assert extract_reason("-2  買手搖", -2) == "買手搖"


def test_parse_settlement_command():
    assert parse_settlement_command("!算帳 11880") == ("聚餐", 11880)
    assert parse_settlement_command("!算帳 續攤火鍋 11880") == ("續攤火鍋", 11880)
    assert parse_settlement_command("!算帳") is None
    assert parse_settlement_command("!算帳 不是數字") is None


def test_calc_settlement_sums_to_total():
    cases = [
        ([0, 0], 1000, 100),
        ([1, -1], 1000, 100),
        ([0, 0, 0], 1000, 100),
        ([3, -2, 0, 1], 12345, 150),
    ]
    for points, amount, point_value in cases:
        result = calc_settlement(points, amount, point_value)
        assert sum(result) == amount, (points, amount, result)


def test_calc_settlement_sinner_pays_more():
    result = calc_settlement([1, -1], 1000, 100)
    assert result[0] > result[1]


def test_leaderboard_data():
    members = [{"display_name": f"人{i}", "total_points": i} for i in range(7)]
    data = leaderboard_data(members)
    assert [m["total_points"] for m in data["merit"]] == [0, 1, 2, 3, 4]
    assert [m["total_points"] for m in data["sinner"]] == [6, 5, 4, 3, 2]
    assert leaderboard_data([]) == {"merit": [], "sinner": []}


if __name__ == "__main__":
    test_extract_mention()
    test_parse_point_delta()
    test_extract_reason()
    test_parse_settlement_command()
    test_calc_settlement_sums_to_total()
    test_calc_settlement_sinner_pays_more()
    test_leaderboard_data()
    print("all tests passed")
