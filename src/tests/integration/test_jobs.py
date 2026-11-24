from datetime import timedelta

from rarest_blue.application import review
from rarest_blue.domain import days, rules
from rarest_blue.entrypoints.cli import generate as generate_cli
from tests.factories import FakeWriter


def test_generator_stores_tomorrow_once(database, uow):
    writer = FakeWriter()
    tomorrow = days.today() + timedelta(days=1)

    assert generate_cli.main([], settings=database, writer=writer) == 0
    with uow() as tx:
        stored = tx.prompts.get(tomorrow)
    assert [p.id for p in stored] == [f"topic{i}" for i in range(rules.PROMPTS_PER_DAY)]

    assert generate_cli.main([], settings=database, writer=writer) == 0  # second run is a no-op
    assert writer.models == [database.generator_model, database.verifier_model]


def test_generator_retries_then_fails(database):
    writer = FakeWriter(error=ValueError("bad json"))
    assert generate_cli.main([], settings=database, writer=writer) == 1
    assert writer.models == [database.generator_model] * 3


def test_accepting_a_missed_answer_rescores(client, uow):
    pid = client.get("/api/daily").json()["prompts"][0]["id"]

    def guess(player, answer):
        return client.post("/api/guess", json={"player_id": player, "prompt_id": pid, "answer": answer}).json()

    assert not guess("player-aaaa", "Qwertyuiop Hall")["valid"]
    assert not guess("player-bbbb", "qwertyuiop")["valid"]
    client.post("/api/finish", json={"player_id": "player-aaaa", "nickname": "a"})

    today = days.today()
    with uow() as tx:
        assert review.rejected(tx, today, 5)[pid] == [("Qwertyuiop Hall", 1), ("qwertyuiop", 1)]
        assert review.accept(tx, today, pid, "Qwertyuiop") == 2
        assert review.rejected(tx, today, 5) == {}

    # Same answer, same rescored points, and the leaderboard total follows.
    again = guess("player-aaaa", "anything")
    assert again["answer"] == "Qwertyuiop" and again["points"] > 0
    assert client.get("/api/leaderboard").json()["players"][0]["score"] == again["points"]
    assert guess("player-cccc", "qwertyuiop")["valid"]


def test_failed_transaction_rolls_back(uow):
    today = days.today()
    try:
        with uow() as tx:
            tx.prompts.add(today, [], source="doomed")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    with uow() as tx:
        assert tx.prompts.get(today) is None
