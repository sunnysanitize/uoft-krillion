from datetime import date, timedelta

import pytest

from rarest_blue.application import generation
from rarest_blue.domain import rules
from rarest_blue.domain.models import Prompt
from tests.factories import FakeWriter, all_clear, gen_prompt, gen_set, verdict


def test_clean_prompt_drops_colliding_aliases():
    gen = gen_prompt("x")
    gen.answers[1].aliases.append(gen.answers[0].name)  # collides with another answer
    gen.answers.append(generation.GenAnswer(name=gen.answers[2].name.upper(), aliases=[], why=""))  # duplicate
    prompt = generation.clean_prompt(gen)
    assert len(prompt.answers) == generation.MIN_ANSWERS + 2
    assert prompt.answers[1] == ("Answer x 1", "alias x 1")
    assert prompt.golden == f"Answer x {generation.MIN_ANSWERS}"


def test_clean_prompt_drops_decoys_that_would_score():
    gen = gen_prompt("x")
    gen.decoys += ["alias x 3", "Answer x 7", "Answr x 8", "wrong x 0", "  "]
    assert generation.clean_prompt(gen).decoys == ["Wrong x 0", "Wrong x 1", "Wrong x 2"]


def test_clean_prompt_rejects_bad_prompts():
    with pytest.raises(ValueError, match="usable answers"):
        generation.clean_prompt(gen_prompt("x", n=generation.MIN_ANSWERS - 1))
    with pytest.raises(ValueError, match="too obvious"):
        generation.clean_prompt(gen_prompt("x", golden_at=0))
    with pytest.raises(ValueError, match="too obvious"):
        generation.clean_prompt(gen_prompt("x", golden_at=5))  # not in the last third
    generic = gen_prompt("x")
    generic.text = "Name a Canadian province"
    with pytest.raises(ValueError, match="doesn't name UofT"):
        generation.clean_prompt(generic)
    bad = gen_prompt("x")
    bad.golden = "Something made up"
    with pytest.raises(ValueError, match="isn't an answer"):
        generation.clean_prompt(bad)


def checked(gen: generation.GenSet) -> list[tuple[str, Prompt]]:
    return generation.check_candidates(gen, all_clear(gen))


def test_pick_set_needs_a_full_unique_spread_set():
    full = checked(gen_set())
    assert [p.id for p in generation.pick_set(full, [])] == [f"topic{i}" for i in range(rules.PROMPTS_PER_DAY)]
    with pytest.raises(ValueError, match="need"):
        generation.pick_set(full[:-1], [])
    dupes = checked(generation.GenSet(prompts=[gen_prompt("same") for _ in range(rules.PROMPTS_PER_DAY)]))
    with pytest.raises(ValueError, match="need"):
        generation.pick_set(dupes, [])
    samey = checked(generation.GenSet(prompts=[gen_prompt(f"topic{i}") for i in range(rules.PROMPTS_PER_DAY)]))
    with pytest.raises(ValueError, match="need"):
        generation.pick_set(samey, [])


def test_pick_set_skips_reruns_of_recent_prompts():
    spare = gen_prompt("spare", category="toronto")
    candidates = checked(generation.GenSet(prompts=[*gen_set().prompts, spare]))
    # A recent day asked the same thing under another name: same answers, different id and wording.
    rerun = generation.clean_prompt(gen_prompt("topic0"))
    rerun = Prompt(**{**rerun.__dict__, "id": "old_name", "text": "Name some UofT thing"})
    picked = generation.pick_set(candidates, [rerun])
    assert "topic0" not in [p.id for p in picked]
    assert picked[-1].id == "spare"


def test_verdict_drops_wrong_answers_and_promotes_right_decoys():
    gen = gen_prompt("x")
    gen.decoys.append("Actually Right")
    v = verdict("x", wrong_answers=["answer x 1"], right_decoys=["actually right"])
    prompt = generation.clean_prompt(generation.apply_verdict(gen, v))
    canon = [names[0] for names in prompt.answers]
    assert "Answer x 1" not in canon
    assert canon[-1] == "Actually Right"
    assert prompt.decoys == ["Wrong x 0", "Wrong x 1", "Wrong x 2"]
    with pytest.raises(ValueError, match="ambiguous"):
        generation.apply_verdict(gen, verdict("x", ambiguous=True, problem="open-ended"))
    # A wrong golden answer passes the bonus to the deepest real answer left.
    swapped = generation.apply_verdict(gen, verdict("x", wrong_answers=[gen.golden]))
    assert swapped.golden == gen.answers[-1].name
    assert generation.clean_prompt(swapped).golden == gen.answers[-1].name


def test_check_candidates_skips_rejected_and_unjudged_prompts():
    verdicts = generation.Verdicts(prompts=[verdict("topic0", ambiguous=True, problem="?"), verdict("topic1")])
    assert [p.id for _, p in generation.check_candidates(gen_set(), verdicts)] == ["topic1"]


def test_daily_focus_varies_by_day():
    week = [date(2026, 11, 1) + timedelta(days=i) for i in range(7)]
    assert len({tuple(generation.focus(d)) for d in week}) > 1
    assert generation.focus(week[0]) == generation.focus(week[0])


def test_parse_reply_strips_code_fences():
    body = gen_set().model_dump_json()
    assert generation.parse_reply(f"```json\n{body}\n```") == gen_set()


def test_generator_writes_then_verifies():
    writer = FakeWriter()
    prompts, source = generation.PromptSetGenerator(writer, "gen", "check").generate(date(2026, 11, 24), [])
    assert len(prompts) == rules.PROMPTS_PER_DAY
    assert writer.models == ["gen", "check"]
    assert source == "gen + check"


def test_generator_retries_then_gives_up():
    writer = FakeWriter(error=ValueError("bad json"))
    gen = generation.PromptSetGenerator(writer, "gen", "check")
    with pytest.raises(generation.GenerationFailed):
        gen.generate(date(2026, 11, 24), [])
    assert writer.models == ["gen"] * generation.ATTEMPTS


def test_request_lists_prompts_to_avoid():
    day = date(2026, 11, 24)
    recent = [generation.clean_prompt(gen_prompt("thing"))]
    assert "- Name a UofT thing" in generation.build_request(day, recent)
    assert "used recently" not in generation.build_request(day, [])
