"""auto_click.py のユニットテスト"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_click import _extract_exploration_result, _url_matches_success


def test_extract_exploration_result_victory():
    text = "自爆餅は勝利した。 13の経験値を獲得した。[C] 弱体の種を手に入れた！"
    msg, exp, drops = _extract_exploration_result(text)
    assert "勝利" in msg
    assert exp == 13
    assert "[C] 弱体の種" in drops


def test_extract_exploration_result_multiple_drops():
    text = "〇〇は勝利した。10の経験値を獲得した。[A] 種を手に入れた。[B] 薬を手に入れた。"
    msg, exp, drops = _extract_exploration_result(text)
    assert exp == 10
    assert "[A] 種" in drops
    assert "[B] 薬" in drops


def test_extract_exploration_result_empty():
    msg, exp, drops = _extract_exploration_result("")
    assert msg == ""
    assert exp == 0
    assert drops == []


def test_url_matches_success_home():
    assert _url_matches_success("https://games-alchemist.com/home/", "home")
    assert not _url_matches_success("https://games-alchemist.com/monster/", "home")


def test_url_matches_success_list():
    assert _url_matches_success("https://example.com/monster/", ["monster", "arena"])
    assert _url_matches_success("https://example.com/arena/", ["monster", "arena"])
    assert not _url_matches_success("https://example.com/other/", ["monster", "arena"])
