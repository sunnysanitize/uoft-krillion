from datetime import date

import pytest
from fastapi.testclient import TestClient

from rarest_blue import game
from rarest_blue.prompts import PROMPTS, PROMPTS_BY_ID


def test_aliases_and_typos_match():
    colleges = PROMPTS_BY_ID["colleges"]
    assert game.match_answer(colleges, "Vic") == "Victoria College"
    assert game.match_answer(colleges, "st. mike's") == "St. Michael's College"
    assert game.match_answer(colleges, "Woodsworht") == "Woodsworth College"
    assert game.match_answer(colleges, "Ryerson") is None
    assert game.match_answer(colleges, "   ") is None


def test_short_codes_do_not_fuzz():
    courses = PROMPTS_BY_ID["first_year_pain"]
    assert game.match_answer(courses, "mat137") == "MAT137"
    assert game.match_answer(courses, "MAT") is None


def test_no_alias_collisions_within_a_prompt():
    for p in PROMPTS:
        seen: dict[str, str] = {}
        for names in p.answers:
            for name in names:
                key = game.normalize(name)
                assert seen.setdefault(key, names[0]) == names[0], f"{p.id}: '{name}' collides"


def test_golden_answers_are_valid_deep_cuts():
    for p in PROMPTS:
        names = [names[0] for names in p.answers]
        assert p.golden in names, f"{p.id}: golden '{p.golden}' isn't an answer"
        assert names.index(p.golden) >= 3, f"{p.id}: golden answer is too obvious"


def test_zones():
    assert game.zone(0) == "Philosopher's Walk Shallows"
    assert game.zone(2500) == "Bahen Trench"
    assert game.zone(99999) == "The Steam Tunnels"


def test_daily_prompts_are_stable_and_vary():
    d1, d2 = date(2026, 11, 23), date(2026, 11, 24)
    assert [p.id for p in game.daily_prompts(d1)] == [p.id for p in game.daily_prompts(d1)]
    assert len(game.daily_prompts(d1)) == game.PROMPTS_PER_DAY
    assert game.daily_prompts(d1) != game.daily_prompts(d2)


def test_rarer_scores_higher():
    assert game.score(0.01) > game.score(0.2) > game.score(0.6)
    assert game.score(1.0) == 1


@pytest.fixture
def client(tmp_path, monkeypatch):
    from rarest_blue import api, db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    return TestClient(api.app)


def test_full_round(client):
    daily = client.get("/api/daily").json()
    pid = daily["prompts"][0]["id"]
    obvious = PROMPTS_BY_ID[pid].answers[0][0]
    deep = PROMPTS_BY_ID[pid].answers[-1][0]

    a = client.post("/api/guess", json={"player_id": "player-aaaa", "prompt_id": pid, "answer": obvious}).json()
    b = client.post("/api/guess", json={"player_id": "player-bbbb", "prompt_id": pid, "answer": deep}).json()
    assert a["valid"] and b["valid"]
    assert b["points"] > a["points"]

    # Re-guessing can't farm points.
    again = client.post("/api/guess", json={"player_id": "player-bbbb", "prompt_id": pid, "answer": obvious}).json()
    assert again["answer"] == deep and again["points"] == b["points"]

    golden = PROMPTS_BY_ID[pid].golden
    g = client.post("/api/guess", json={"player_id": "player-dddd", "prompt_id": pid, "answer": golden}).json()
    assert g["golden"] and g["points"] > game.GOLDEN_BONUS
    assert not a["golden"] and a["golden_answer"] == golden

    bad = client.post("/api/guess", json={"player_id": "player-cccc", "prompt_id": pid, "answer": "zzzz"}).json()
    assert not bad["valid"] and bad["points"] == 0

    done = client.post("/api/finish", json={"player_id": "player-bbbb", "nickname": "deepdiver", "college": "Innis"}).json()
    assert done["score"] == b["points"]
    board = client.get("/api/leaderboard").json()
    assert board["players"][0]["nickname"] == "deepdiver"
    assert board["colleges"][0]["college"] == "Innis"
