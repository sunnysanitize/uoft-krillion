from datetime import date

import pytest

from rarest_blue.application import generation
from rarest_blue.domain import rules
from tests.factories import FakeWriter, gen_prompt, gen_set


def test_clean_prompt_drops_colliding_aliases():
    gen = gen_prompt("x")
    gen.answers[1].aliases.append(gen.answers[0].name)  # collides with another answer
    gen.answers.append(generation.GenAnswer(name=gen.answers[2].name.upper(), aliases=[]))  # duplicate answer
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


def test_clean_set_needs_a_full_unique_set():
    short = generation.GenSet(prompts=gen_set().prompts[:-1])
    with pytest.raises(ValueError, match="need"):
        generation.clean_set(short)
    dupes = generation.GenSet(prompts=[gen_prompt("same") for _ in range(rules.PROMPTS_PER_DAY)])
    with pytest.raises(ValueError, match="duplicate"):
        generation.clean_set(dupes)
    samey = generation.GenSet(prompts=[gen_prompt(f"topic{i}") for i in range(rules.PROMPTS_PER_DAY)])
    with pytest.raises(ValueError, match="max is"):
        generation.clean_set(samey)


def test_parse_reply_strips_code_fences():
    body = gen_set().model_dump_json()
    assert generation.parse_reply(f"```json\n{body}\n```") == gen_set()


def test_generator_cycles_models_then_gives_up():
    writer = FakeWriter(error=ValueError("bad json"))
    gen = generation.PromptSetGenerator(writer, ["model-a", "model-b"])
    with pytest.raises(generation.GenerationFailed):
        gen.generate(date(2026, 11, 24), [])
    assert writer.models == ["model-a", "model-b", "model-a"]


def test_request_lists_prompts_to_avoid():
    assert "- Name a thing" in generation.build_request(["Name a thing"])
    assert "Recently used" not in generation.build_request([])
