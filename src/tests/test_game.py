import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from rarest_blue import api, db, game, generate, review
from rarest_blue.prompts import PROMPTS, PROMPTS_BY_ID, Prompt


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


def test_short_forms_and_extra_words_match():
    buildings = PROMPTS_BY_ID["buildings"]
    assert game.match_answer(buildings, "Lash Miller Chemical") == "Lash Miller Chemical Laboratories"
    assert game.match_answer(buildings, "Koffler Student") == "Koffler Student Services Centre"
    assert game.match_answer(PROMPTS_BY_ID["subway"], "Spadina Station") == "Spadina"
    assert game.match_answer(PROMPTS_BY_ID["libraries"], "Innis Library") == "Innis College Library"
    # Ambiguous or generic leading words don't count.
    assert game.match_answer(PROMPTS_BY_ID["ontario_unis"], "University") is None
    assert game.match_answer(PROMPTS_BY_ID["faculties"], "Faculty") is None


def test_fallback_prompts_have_decoys_that_dont_score():
    for p in PROMPTS:
        assert len(p.decoys) >= 8, f"{p.id}: needs decoys so autocomplete doesn't list only answers"
        for d in p.decoys:
            assert game.match_answer(p, d) is None, f"{p.id}: decoy '{d}' scores"


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


def test_fallback_prompts_are_stable_and_vary():
    d1, d2 = date(2026, 11, 23), date(2026, 11, 24)
    assert [p.id for p in game.fallback_prompts(d1)] == [p.id for p in game.fallback_prompts(d1)]
    assert len(game.fallback_prompts(d1)) == game.PROMPTS_PER_DAY
    assert game.fallback_prompts(d1) != game.fallback_prompts(d2)


def test_rarer_scores_higher():
    assert [game.score(s) for s in (0.01, 0.1, 0.2, 0.6)] == [85, 60, 30, 10]
    assert game.score(0.6, golden=True) == 100


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def database(monkeypatch):
    if not TEST_DATABASE_URL:
        pytest.skip("set TEST_DATABASE_URL to run database tests")
    monkeypatch.setattr(db, "DATABASE_URL", TEST_DATABASE_URL)
    db.init_schema()
    with db.connect() as conn:
        conn.execute("TRUNCATE daily_prompts, guesses, finishes")


@pytest.fixture
def client(database):
    with TestClient(api.app) as c:
        yield c


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
    assert g["golden"] and g["points"] == game.GOLDEN_POINTS and g["rarity"] == "One in a Krillion"
    assert not a["golden"] and a["golden_answer"] == golden

    bad = client.post("/api/guess", json={"player_id": "player-cccc", "prompt_id": pid, "answer": "zzzz"}).json()
    assert not bad["valid"] and bad["points"] == 0

    done = client.post("/api/finish", json={"player_id": "player-bbbb", "nickname": "deepdiver"}).json()
    assert done["score"] == b["points"]
    board = client.get("/api/leaderboard").json()
    assert board["players"][0] == {"nickname": "deepdiver", "score": b["points"]}
    assert "colleges" not in board


def _gen_prompt(pid: str, n: int = generate.MIN_ANSWERS + 2, golden_at: int = -2, category: str = "places") -> generate.GenPrompt:
    answers = [generate.GenAnswer(name=f"Answer {pid} {i}", aliases=[f"alias {pid} {i}"]) for i in range(n)]
    return generate.GenPrompt(
        id=pid, category=category, text=f"Name a UofT {pid}", hint="Go deep.", golden=answers[golden_at].name, answers=answers,
        decoys=[f"Wrong {pid} {i}" for i in range(3)],
    )


def _gen_set() -> generate.GenSet:
    categories = list(generate.Category.__args__)
    return generate.GenSet(
        prompts=[_gen_prompt(f"topic{i}", category=categories[i % len(categories)]) for i in range(game.PROMPTS_PER_DAY)]
    )


def test_clean_prompt_drops_colliding_aliases():
    gen = _gen_prompt("x")
    gen.answers[1].aliases.append(gen.answers[0].name)  # collides with another answer
    gen.answers.append(generate.GenAnswer(name=gen.answers[2].name.upper(), aliases=[]))  # duplicate answer
    prompt = generate.clean_prompt(gen)
    assert len(prompt.answers) == generate.MIN_ANSWERS + 2
    assert prompt.answers[1] == ("Answer x 1", "alias x 1")
    assert prompt.golden == f"Answer x {generate.MIN_ANSWERS}"


def test_clean_prompt_drops_decoys_that_would_score():
    gen = _gen_prompt("x")
    gen.decoys += ["alias x 3", "Answer x 7", "Answr x 8", "wrong x 0", "  "]
    assert generate.clean_prompt(gen).decoys == ["Wrong x 0", "Wrong x 1", "Wrong x 2"]


def test_clean_prompt_rejects_bad_prompts():
    with pytest.raises(ValueError, match="usable answers"):
        generate.clean_prompt(_gen_prompt("x", n=generate.MIN_ANSWERS - 1))
    with pytest.raises(ValueError, match="too obvious"):
        generate.clean_prompt(_gen_prompt("x", golden_at=0))
    with pytest.raises(ValueError, match="too obvious"):
        generate.clean_prompt(_gen_prompt("x", golden_at=5))  # not in the last third
    generic = _gen_prompt("x")
    generic.text = "Name a Canadian province"
    with pytest.raises(ValueError, match="doesn't name UofT"):
        generate.clean_prompt(generic)
    bad = _gen_prompt("x")
    bad.golden = "Something made up"
    with pytest.raises(ValueError, match="isn't an answer"):
        generate.clean_prompt(bad)


def test_clean_set_needs_a_full_unique_set():
    short = generate.GenSet(prompts=_gen_set().prompts[:-1])
    with pytest.raises(ValueError, match="need"):
        generate.clean_set(short)
    dupes = generate.GenSet(prompts=[_gen_prompt("same") for _ in range(game.PROMPTS_PER_DAY)])
    with pytest.raises(ValueError, match="duplicate"):
        generate.clean_set(dupes)
    samey = generate.GenSet(prompts=[_gen_prompt(f"topic{i}") for i in range(game.PROMPTS_PER_DAY)])
    with pytest.raises(ValueError, match="max is"):
        generate.clean_set(samey)


def test_generator_stores_tomorrow_once(database, monkeypatch):
    calls = []
    monkeypatch.setattr(generate, "ask_llm", lambda request, model: calls.append(model) or _gen_set())
    tomorrow = game.today() + timedelta(days=1)

    assert generate.main([]) == 0
    with db.connect() as conn:
        stored = db.load_prompts(conn, tomorrow)
    assert [p.id for p in stored] == [f"topic{i}" for i in range(game.PROMPTS_PER_DAY)]

    assert generate.main([]) == 0  # second run is a no-op
    assert len(calls) == 1


def test_generator_retries_then_fails(database, monkeypatch):
    attempts = []

    def flaky(request, model):
        attempts.append(model)
        raise ValueError("bad json")

    monkeypatch.setattr(generate, "MODELS", ["model-a", "model-b"])
    monkeypatch.setattr(generate, "ask_llm", flaky)
    assert generate.main([]) == 1
    assert attempts == ["model-a", "model-b", "model-a"]


def test_serves_stored_set(client):
    today = game.today()
    prompts = generate.clean_set(_gen_set())
    with db.connect() as conn:
        assert db.save_prompts(conn, today, prompts, source="test")

    daily = client.get("/api/daily").json()
    assert [p["id"] for p in daily["prompts"]] == [p.id for p in prompts]
    assert "suggestions" not in daily["prompts"][0]  # the answer list never reaches the browser

    check = lambda answer: client.post("/api/check", json={"prompt_id": "topic0", "answer": answer}).json()
    assert check("alias topic0 3") == {"recognized": True, "correct": True, "suggestion": None}
    assert check("Wrong topic0 1") == {"recognized": True, "correct": False, "suggestion": None}
    assert check("Wrong topic0 1x")["suggestion"] == "Wrong topic0 1"
    assert check("zzzzzz") == {"recognized": False, "correct": False, "suggestion": None}

    golden = generate.MIN_ANSWERS
    g = client.post("/api/guess", json={"player_id": "player-aaaa", "prompt_id": "topic0", "answer": f"alias topic0 {golden}"}).json()
    assert g["answer"] == f"Answer topic0 {golden}" and g["golden"]

    old = client.post("/api/guess", json={"player_id": "player-aaaa", "prompt_id": "colleges", "answer": "vic"})
    assert old.status_code == 400


def test_fallback_locks_the_day(client):
    client.get("/api/daily")
    with db.connect() as conn:
        assert not db.save_prompts(conn, game.today(), [Prompt("x", "x", "x", "x")], source="late")
        assert [p.id for p in db.load_prompts(conn, game.today())] == [p.id for p in game.fallback_prompts(game.today())]


def test_accepting_a_missed_answer_rescores(client):
    pid = client.get("/api/daily").json()["prompts"][0]["id"]
    guess = lambda player, answer: client.post(
        "/api/guess", json={"player_id": player, "prompt_id": pid, "answer": answer}
    ).json()
    assert not guess("player-aaaa", "Qwertyuiop Hall")["valid"]
    assert not guess("player-bbbb", "qwertyuiop")["valid"]
    client.post("/api/finish", json={"player_id": "player-aaaa", "nickname": "a"})

    with db.connect() as conn:
        assert review.rejected(conn, game.today(), 5)[pid] == [("Qwertyuiop Hall", 1), ("qwertyuiop", 1)]
        assert review.accept(conn, game.today(), pid, "Qwertyuiop") == 2
        assert review.rejected(conn, game.today(), 5) == {}

    # Same answer, same rescored points, and the leaderboard total follows.
    again = guess("player-aaaa", "anything")
    assert again["answer"] == "Qwertyuiop" and again["points"] > 0
    assert client.get("/api/leaderboard").json()["players"][0]["score"] == again["points"]
    assert guess("player-cccc", "qwertyuiop")["valid"]


def test_accept_as_alias_checks_the_answer():
    colleges = PROMPTS_BY_ID["colleges"]
    updated = review.with_answer(colleges, "Woody C", "woodsworth")
    assert game.match_answer(updated, "woody c") == "Woodsworth College"
    with pytest.raises(ValueError, match="isn't an answer"):
        review.with_answer(colleges, "Woody C", "Ryerson")
    with pytest.raises(ValueError, match="already counts"):
        review.with_answer(colleges, "vic", "Trinity")


def test_rarity_tiers():
    labels = [game.rarity_label(s) for s in (0.005, 0.03, 0.1, 0.25, 0.6)]
    assert labels == ["Deep Cut", "Deep Cut", "Rare", "Uncommon", "Common"]
    assert game.rarity_label(0.6, golden=True) == "One in a Krillion"


def test_recognize_treats_answers_and_decoys_alike():
    colleges = PROMPTS_BY_ID["colleges"]
    assert game.recognize(colleges, "vic") == (True, None)
    assert game.recognize(colleges, "Massey College") == (True, None)
    # Typos of either kind are suggested, never silently accepted.
    assert game.recognize(colleges, "Woodsworht") == (False, "Woodsworth College")
    assert game.recognize(colleges, "Masey College") == (False, "Massey College")
    assert game.recognize(colleges, "Ryerson Hall") == (False, None)


def test_answers_list_only_after_playing(client):
    pid = client.get("/api/daily").json()["prompts"][0]["id"]
    ask = lambda player: client.post("/api/answers", json={"player_id": player, "prompt_id": pid})
    assert ask("player-aaaa").status_code == 403  # no peeking before you play

    obvious = PROMPTS_BY_ID[pid].answers[0][0]
    client.post("/api/guess", json={"player_id": "player-aaaa", "prompt_id": pid, "answer": obvious})
    rows = ask("player-aaaa").json()["answers"]
    assert len(rows) == len(PROMPTS_BY_ID[pid].answers)
    assert rows == sorted(rows, key=lambda r: -r["points"])
    assert [r["answer"] for r in rows if r["yours"]] == [obvious]
    golden = next(r for r in rows if r["golden"])
    assert golden["points"] == game.GOLDEN_POINTS and golden["rarity"] == "One in a Krillion"
