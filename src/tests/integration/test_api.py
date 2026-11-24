from rarest_blue.application import generation
from rarest_blue.domain import days, rules
from rarest_blue.domain.models import Prompt
from rarest_blue.domain.prompt_bank import PROMPTS, PROMPTS_BY_ID
from tests.factories import gen_set


def _guess(client, player, pid, answer):
    return client.post("/api/guess", json={"player_id": player, "prompt_id": pid, "answer": answer}).json()


def test_full_round(client):
    daily = client.get("/api/daily").json()
    pid = daily["prompts"][0]["id"]
    obvious = PROMPTS_BY_ID[pid].answers[0][0]
    deep = PROMPTS_BY_ID[pid].answers[-1][0]

    a = _guess(client, "player-aaaa", pid, obvious)
    b = _guess(client, "player-bbbb", pid, deep)
    assert a["valid"] and b["valid"]
    assert b["points"] > a["points"]

    # Re-guessing can't farm points.
    again = _guess(client, "player-bbbb", pid, obvious)
    assert again["answer"] == deep and again["points"] == b["points"]

    golden = PROMPTS_BY_ID[pid].golden
    g = _guess(client, "player-dddd", pid, golden)
    assert g["golden"] and g["points"] == rules.GOLDEN_POINTS and g["rarity"] == "One in a Krillion"
    assert not a["golden"] and a["golden_answer"] == golden

    bad = _guess(client, "player-cccc", pid, "zzzz")
    assert not bad["valid"] and bad["points"] == 0

    done = client.post("/api/finish", json={"player_id": "player-bbbb", "nickname": "deepdiver"}).json()
    assert done["score"] == b["points"]
    board = client.get("/api/leaderboard").json()
    assert board["players"][0] == {"nickname": "deepdiver", "score": b["points"]}
    assert "colleges" not in board


def test_daily_payload_shape_is_stable(client):
    """The web app depends on these exact keys; answers must never appear in it."""
    daily = client.get("/api/daily").json()
    assert set(daily) == {"day", "number", "time_limit", "meters_per_point", "zones", "prompts"}
    assert len(daily["prompts"]) == rules.PROMPTS_PER_DAY
    for p in daily["prompts"]:
        assert set(p) == {"id", "text", "hint"}


def test_serves_stored_set(client, uow):
    today = days.today()
    prompts = generation.clean_set(gen_set())
    with uow() as tx:
        assert tx.prompts.add(today, prompts, source="test")

    daily = client.get("/api/daily").json()
    assert [p["id"] for p in daily["prompts"]] == [p.id for p in prompts]

    def check(answer):
        return client.post("/api/check", json={"prompt_id": "topic0", "answer": answer}).json()

    assert check("alias topic0 3") == {"recognized": True, "correct": True, "suggestion": None}
    assert check("Wrong topic0 1") == {"recognized": True, "correct": False, "suggestion": None}
    assert check("Wrong topic0 1x")["suggestion"] == "Wrong topic0 1"
    assert check("zzzzzz") == {"recognized": False, "correct": False, "suggestion": None}

    golden = generation.MIN_ANSWERS
    g = _guess(client, "player-aaaa", "topic0", f"alias topic0 {golden}")
    assert g["answer"] == f"Answer topic0 {golden}" and g["golden"]

    old = client.post("/api/guess", json={"player_id": "player-aaaa", "prompt_id": "colleges", "answer": "vic"})
    assert old.status_code == 400


def test_fallback_locks_the_day(client, uow):
    client.get("/api/daily")
    today = days.today()
    with uow() as tx:
        assert not tx.prompts.add(today, [Prompt("x", "x", "x", "x")], source="late")
        assert [p.id for p in tx.prompts.get(today)] == [p.id for p in days.pick_fallback(today, PROMPTS)]


def test_answers_list_only_after_playing(client):
    pid = client.get("/api/daily").json()["prompts"][0]["id"]

    def ask(player):
        return client.post("/api/answers", json={"player_id": player, "prompt_id": pid})

    assert ask("player-aaaa").status_code == 403  # no peeking before you play

    obvious = PROMPTS_BY_ID[pid].answers[0][0]
    _guess(client, "player-aaaa", pid, obvious)
    rows = ask("player-aaaa").json()["answers"]
    assert len(rows) == len(PROMPTS_BY_ID[pid].answers)
    assert rows == sorted(rows, key=lambda r: -r["points"])
    assert [r["answer"] for r in rows if r["yours"]] == [obvious]
    golden = next(r for r in rows if r["golden"])
    assert golden["points"] == rules.GOLDEN_POINTS and golden["rarity"] == "One in a Krillion"


def test_rejects_bad_input(client):
    short_id = client.post("/api/guess", json={"player_id": "short", "prompt_id": "x", "answer": "y"})
    long_answer = client.post("/api/guess", json={"player_id": "player-aaaa", "prompt_id": "x", "answer": "y" * 81})
    assert short_id.status_code == long_answer.status_code == 422


def test_api_docs_and_dev_reset_are_not_exposed(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.post("/api/dev/reset", json={"player_id": "player-aaaa"}).status_code == 404
