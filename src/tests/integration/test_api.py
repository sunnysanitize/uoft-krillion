from rarest_blue.application import generation
from rarest_blue.domain import days, rules
from rarest_blue.domain.models import Prompt
from rarest_blue.domain.prompt_bank import PROMPTS, PROMPTS_BY_ID
from tests.factories import all_clear, gen_set


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
    """Load all local matching data and scores with the questions, before the first Dive."""
    daily = client.get("/api/daily").json()
    assert set(daily) == {"day", "number", "time_limit", "meters_per_point", "zones", "prompts"}
    assert len(daily["prompts"]) == rules.PROMPTS_PER_DAY
    for p in daily["prompts"]:
        assert set(p) == {"id", "text", "hint", "play"}
        prompt = PROMPTS_BY_ID[p["id"]]
        assert [a["names"] for a in p["play"]["answers"]] == [list(names) for names in prompt.answers]
        assert p["play"]["decoys"] == prompt.decoys
        assert p["play"]["golden_answer"] == prompt.golden
        assert p["play"]["valid_answers"] == len(prompt.answers)


def test_preloaded_score_matches_server_submission(client, uow):
    daily = client.get("/api/daily").json()
    for prompt in daily["prompts"]:
        answer = prompt["play"]["answers"][0]
        result = _guess(client, "player-aaaa", prompt["id"], answer["names"][0])
        for field in ("points", "share_pct", "rarity", "golden"):
            assert result[field] == answer[field]
    # Preloading again is read-only and includes the recorded popularity.
    refreshed = client.get("/api/daily").json()
    assert all(p["play"]["players"] == 1 for p in refreshed["prompts"])
    with uow() as tx:
        assert all(tx.guesses.player_count(days.today(), p["id"]) == 1 for p in refreshed["prompts"])


def test_serves_stored_set(client, uow):
    today = days.today()
    prompts = generation.pick_set(generation.check_candidates(gen_set(), all_clear(gen_set())), [])
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


def test_attempt_checks_and_records_a_correct_answer_in_one_request(client, uow):
    pid = client.get("/api/daily").json()["prompts"][0]["id"]
    prompt = PROMPTS_BY_ID[pid]
    body = {"player_id": "player-aaaa", "prompt_id": pid, "answer": prompt.answers[0][0]}
    response = client.post("/api/attempt", json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["accepted"] and result["result"]["valid"]
    assert result["result"]["answer"] == body["answer"]
    # Retrying a request returns the original score and never adds another guess.
    again = client.post("/api/attempt", json={**body, "answer": prompt.golden}).json()
    assert again["result"]["answer"] == body["answer"]
    assert again["result"]["points"] == result["result"]["points"]
    with uow() as tx:
        assert tx.guesses.player_count(days.today(), pid) == 1


def test_attempt_rejects_wrong_answers_without_spending_the_prompt(client, uow):
    pid = client.get("/api/daily").json()["prompts"][0]["id"]
    prompt = PROMPTS_BY_ID[pid]
    body = {"player_id": "player-aaaa", "prompt_id": pid, "answer": prompt.decoys[0]}
    assert client.post("/api/attempt", json=body).json() == {
        "accepted": False,
        "check": {"recognized": True, "correct": False, "suggestion": None},
    }
    unknown = client.post("/api/attempt", json={**body, "answer": "zzzzzz"}).json()
    assert unknown == {"accepted": False, "check": {"recognized": False, "correct": False, "suggestion": None}}
    with uow() as tx:
        assert tx.guesses.find(days.today(), pid, body["player_id"]) is None
    correct = client.post("/api/attempt", json={**body, "answer": prompt.golden}).json()
    assert correct["accepted"] and correct["result"]["golden"]


def test_attempt_offers_suggestions_and_preserves_timeout_submission(client, uow):
    with uow() as tx:
        tx.prompts.add(days.today(), [PROMPTS_BY_ID["colleges"]], source="test")
    body = {"player_id": "player-aaaa", "prompt_id": "colleges", "answer": "Woodsworht"}
    result = client.post("/api/attempt", json=body).json()
    assert result == {
        "accepted": False,
        "check": {"recognized": False, "correct": False, "suggestion": "Woodsworth College"},
    }
    timed_out = client.post("/api/guess", json={**body, "answer": ""}).json()
    assert not timed_out["valid"] and timed_out["points"] == 0
    unknown = client.post("/api/attempt", json={**body, "prompt_id": "missing"})
    assert unknown.status_code == 400


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


def test_bulk_stats_match_per_prompt_counts(client, uow):
    pids = [p["id"] for p in client.get("/api/daily").json()["prompts"]]
    first = PROMPTS_BY_ID[pids[0]].answers[0][0]
    _guess(client, "player-aaaa", pids[0], first)
    _guess(client, "player-bbbb", pids[0], first)
    _guess(client, "player-cccc", pids[1], "zzzz")  # a miss counts as a player but not an answer
    today = days.today()
    with uow() as tx:
        day = tx.guesses.stats(today)
        one = tx.guesses.stats(today, pids[0])
    assert day[pids[0]].tallies == {first: 2} and day[pids[0]].players == 2
    assert day[pids[1]].tallies == {} and day[pids[1]].players == 1
    assert one == {pids[0]: day[pids[0]]}


def test_pooled_connections_are_reused_across_requests(client):
    for _ in range(25):  # more requests than the pool has connections
        assert client.get("/api/leaderboard").status_code == 200
