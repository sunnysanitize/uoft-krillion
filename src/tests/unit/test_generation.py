import json
from datetime import date, timedelta

import pytest

from rarest_blue.application import generation
from rarest_blue.domain import rules
from rarest_blue.domain.matching import match_answer
from rarest_blue.domain.models import Prompt
from tests.factories import FakeWriter, addition, all_clear, gen_prompt, gen_set, verdict


def test_generator_examples_satisfy_candidate_validation():
    for example in json.loads(generation._examples())["prompts"]:
        prompt = generation.clean_prompt(generation.GenPrompt.model_validate(example))
        assert len(prompt.answers) >= generation.MIN_ANSWERS


def test_clean_prompt_drops_colliding_aliases():
    gen = gen_prompt("x")
    gen.answers[1].aliases.append(gen.answers[0].name)  # collides with another answer
    gen.answers.append(generation.GenAnswer(name=gen.answers[2].name.upper(), aliases=[], why=""))  # duplicate
    prompt = generation.clean_prompt(gen)
    assert len(prompt.answers) == generation.MIN_ANSWERS + 2
    assert prompt.answers[1] == ("Answer x 1", "alias x 1")
    assert prompt.golden == f"Answer x {generation.MIN_ANSWERS}"


def test_clean_prompt_keeps_the_golden_answers_why():
    gen = gen_prompt("x")
    golden = next(a for a in gen.answers if a.name == gen.golden)
    golden.why = "  Hidden in plain sight.  "
    assert generation.clean_prompt(gen).golden_why == "Hidden in plain sight."


def test_clean_prompt_drops_decoys_that_would_score():
    gen = gen_prompt("x")
    gen.decoys += ["alias x 3", "Answer x 7", "Answr x 8", "wrong x 0", "  "]
    assert generation.clean_prompt(gen).decoys == ["Wrong x 0", "Wrong x 1", "Wrong x 2"]


def test_clean_prompt_rejects_bad_prompts():
    with pytest.raises(ValueError, match="usable answers"):
        generation.clean_prompt(gen_prompt("x", n=generation.MIN_ANSWERS - 1))
    # A golden outside the last third hands the bonus to the deepest answer.
    assert generation.clean_prompt(gen_prompt("x", golden_at=0)).golden == f"Answer x {generation.MIN_ANSWERS + 1}"
    assert generation.clean_prompt(gen_prompt("x", golden_at=5)).golden == f"Answer x {generation.MIN_ANSWERS + 1}"
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


def canon_of(gen: generation.GenPrompt, v: generation.Verdict) -> list[str]:
    return [names[0] for names in generation.clean_prompt(generation.apply_verdict(gen, v)).answers]


def test_verdict_drops_wrong_answers_and_promotes_defensible_decoys():
    gen = gen_prompt("x")
    gen.decoys.append("Actually Right")
    applied = generation.apply_verdict(gen, verdict(gen, invalid=("Answer x 1",), defensible=("Actually Right",)))
    prompt = generation.clean_prompt(applied)
    canon = [names[0] for names in prompt.answers]
    assert "Answer x 1" not in canon
    # New answers sit just before the golden one, so it stays the deep cut.
    assert canon[canon.index(prompt.golden) - 1] == "Actually Right"
    assert prompt.golden == gen.golden
    assert prompt.decoys == ["Wrong x 0", "Wrong x 1", "Wrong x 2"]
    with pytest.raises(ValueError, match="ambiguous"):
        generation.apply_verdict(gen, verdict(gen, ambiguous=True, problem="open-ended"))
    # A wrong golden answer passes the bonus to the deepest real answer left.
    swapped = generation.apply_verdict(gen, verdict(gen, invalid=(gen.golden,)))
    assert swapped.golden == gen.answers[-1].name
    assert generation.clean_prompt(swapped).golden == gen.answers[-1].name


def test_verdict_must_judge_the_list_item_by_item():
    gen = gen_prompt("x")
    v = verdict(gen)
    skipped_one = v.model_copy(update={"answers": v.answers[1:], "decoys": v.decoys[1:]})
    applied = generation.apply_verdict(gen, skipped_one)
    # One unjudged answer keeps the writer's word; an unjudged decoy goes, since dropping one costs nothing.
    assert len(applied.answers) == len(gen.answers)
    assert applied.decoys == gen.decoys[1:]
    # A verdict that only names the bad ones (the old free-list habit) didn't check the rest.
    lazy = v.model_copy(update={"answers": [generation.AnswerCheck(name="Answer x 1", valid=False, more_aliases=[])]})
    with pytest.raises(ValueError, match="only judged 1"):
        generation.apply_verdict(gen, lazy)
    # Checks are matched by alias too, and extra aliases from the checker count.
    v.answers[0] = generation.AnswerCheck(name="alias x 0", valid=True, more_aliases=["double shot x"])
    prompt = generation.clean_prompt(generation.apply_verdict(gen, v))
    assert match_answer(prompt, "double shot x") == "Answer x 0"


def test_closed_prompts_take_sourced_additions_but_not_a_sample():
    gen = gen_prompt("x")
    missing = tuple(addition(f"New {i}") for i in range(5))
    canon = canon_of(gen, verdict(gen, missing=missing))
    assert canon[-7:-2] == [f"New {i}" for i in range(5)]
    # So many missing that the writer's list was a sample of the set.
    many = tuple(addition(f"New {i}") for i in range(generation.MAX_CLOSED_ADDITIONS + 1))
    with pytest.raises(ValueError, match="sample"):
        generation.apply_verdict(gen, verdict(gen, missing=many))
    # Checked from memory only: no source, so nothing to trust the list or the additions against.
    with pytest.raises(ValueError, match="no source"):
        generation.apply_verdict(gen, verdict(gen, sources=[]))
    # Members on the verifier's source that the list misses go in, matched by alias and leading words, not fuzzily.
    source = ["Answer x 0", "alias x 3", "Answer x 5 Extension", "Answer x 6 Annex", "Erindale Studio Theatre"]
    gen.answers[6].name = "Answer x 6 Annex Building"
    canon = canon_of(gen, verdict(gen, source_members=source))
    assert canon.count("Erindale Studio Theatre") == 1 and "Answer x 5 Extension" in canon
    assert "Answer x 0" in canon and "alias x 3" not in canon and "Answer x 6 Annex" not in canon
    # A source's fuller or shorter form of a name already listed isn't a new answer.
    gen.answers[7].name = "David R. Peterson"
    source = ["David Peterson", "The Honourable David R. Peterson", "Michael Wilson"]
    canon = canon_of(gen, verdict(gen, source_members=source))
    assert "David Peterson" not in canon and "The Honourable David R. Peterson" not in canon
    assert "Michael Wilson" in canon
    # A closed list longer than its set is padded.
    gen.set_size = len(gen.answers) - 1
    with pytest.raises(ValueError, match="padding"):
        generation.apply_verdict(gen, verdict(gen))
    # Additions the checker contradicts, or can't say why they're real, stay out.
    gen.set_size = 0
    unexplained = generation.GenAnswer(name="No Reason", aliases=[], why=" ")
    canon = canon_of(gen, verdict(gen, invalid=("Answer x 1",), missing=(addition("Wrong x 0"), unexplained)))
    assert "Wrong x 0" not in canon and "No Reason" not in canon


def test_incomplete_lists_are_thrown_out():
    gen = gen_prompt("x")
    with pytest.raises(ValueError, match="incomplete"):
        generation.apply_verdict(gen, verdict(gen, complete=False))
    # The writer's own count saying the list is a sample of its set.
    gen.set_size = len(gen.answers) + 3
    with pytest.raises(ValueError, match="sample"):
        generation.apply_verdict(gen, verdict(gen))


def test_open_prompts_need_a_broad_list_and_take_every_addition():
    thin = gen_prompt("x", n=generation.OPEN_MIN_ANSWERS - 2, kind="open")
    with pytest.raises(ValueError, match="open prompt"):
        canon_of(thin, verdict(thin))
    missing = (addition("Coffee"), addition("Katsu", ("chicken katsu", "katsudon")), addition("Ramen"))
    canon = canon_of(thin, verdict(thin, missing=missing))
    assert {"Coffee", "Katsu", "Ramen"} <= set(canon)
    # The writer calling it closed doesn't dodge the broad-list bar if the checker says it's open.
    closed = gen_prompt("x", n=generation.MIN_ANSWERS + 2)
    with pytest.raises(ValueError, match="open prompt"):
        canon_of(closed, verdict(closed, kind="open"))


def test_clean_prompt_drops_decoys_sharing_a_name_with_an_answer():
    gen = gen_prompt("x")
    gen.answers[0].aliases.append("steamed milk")
    gen.decoys += ["Milk", "Answer x 3 Supreme", "Tea"]
    assert generation.clean_prompt(gen).decoys == ["Wrong x 0", "Wrong x 1", "Wrong x 2", "Tea"]


def test_verify_request_shows_the_hint():
    gen = gen_set()
    gen.prompts[0].hint = "Energy drinks count too."
    assert "Energy drinks count too." in generation.build_verify_request(gen.prompts[0])


def test_check_candidates_skips_rejected_and_unjudged_prompts():
    gen = gen_set()
    verdicts = generation.Verdicts(
        prompts=[verdict(gen.prompts[0], ambiguous=True, problem="?"), verdict(gen.prompts[1])]
    )
    assert [p.id for _, p in generation.check_candidates(gen, verdicts)] == ["topic1"]


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
    # One searching check per prompt.
    assert writer.models == ["gen"] + ["check"] * rules.PROMPTS_PER_DAY
    assert source == "gen + check"


def test_one_failed_check_drops_only_its_prompt():
    gen = gen_set()
    gen.prompts.append(gen_prompt("spare", category="toronto"))
    # No verdict for topic0, so its check raises, like an API error would.
    verdicts = generation.Verdicts(prompts=[verdict(p) for p in gen.prompts[1:]])
    writer = FakeWriter(reply=gen, verdicts=verdicts)
    prompts, _ = generation.PromptSetGenerator(writer, "gen", "check").generate(date(2026, 11, 24), [])
    assert "topic0" not in [p.id for p in prompts] and "spare" in [p.id for p in prompts]


def test_generator_retries_then_gives_up():
    writer = FakeWriter(error=ValueError("bad json"))
    gen = generation.PromptSetGenerator(writer, "gen", "check")
    with pytest.raises(generation.GenerationFailed):
        gen.generate(date(2026, 11, 24), [])
    assert writer.models == ["gen"] * generation.ATTEMPTS


def test_generator_keeps_passing_candidates_across_attempts():
    # Each batch has only half a day of usable prompts; together they fill it.
    batches = [gen_set(), gen_set()]
    for i, batch in enumerate(batches):
        for p in batch.prompts:
            p.id, p.answers = f"{p.id}_{i}", [a.model_copy(update={"name": f"{a.name} {i}"}) for a in p.answers]
            p.golden = p.answers[-2].name
        batch.prompts = batch.prompts[: rules.PROMPTS_PER_DAY // 2 + i]

    class Batches(FakeWriter):
        def write(self, request, model, response_schema, temperature, web_search=False):
            if response_schema is generation.RESPONSE_SCHEMA:
                self.reply = batches.pop(0)
            return super().write(request, model, response_schema, temperature, web_search)

    prompts, _ = generation.PromptSetGenerator(Batches(), "gen", "check").generate(date(2026, 11, 24), [])
    assert len(prompts) == rules.PROMPTS_PER_DAY


def test_request_lists_prompts_to_avoid():
    day = date(2026, 11, 24)
    recent = [generation.clean_prompt(gen_prompt("thing"))]
    assert "- Name a UofT thing" in generation.build_request(day, recent)
    assert "used recently" not in generation.build_request(day, [])
