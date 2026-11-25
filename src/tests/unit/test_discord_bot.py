from datetime import date

import pytest

from rarest_blue.domain.prompt_bank import PROMPTS
from rarest_blue.entrypoints import discord_bot as bot

DAY = date(2026, 11, 26)


def test_every_bank_prompt_fits_in_one_embed():
    for n, p in enumerate(PROMPTS, 1):
        embed = bot.prompt_embed(DAY, n, p)
        assert len(embed.description) <= bot.DESCRIPTION_LIMIT
        assert len(embed) <= 6000  # Discord's total per embed


def test_fit_cuts_whole_lines_and_says_how_many():
    lines = [f"line {i} " + "x" * 50 for i in range(200)]
    out = bot._fit(lines, 1000)
    assert len(out) <= 1000 and out.endswith("more lines")
    assert all(line in lines for line in out.splitlines()[:-1])


def test_prompt_refs_carry_the_day():
    assert bot._parse_ref("2026-11-26/famous_alumni") == (DAY, "famous_alumni")
    with pytest.raises(ValueError, match="pick a prompt"):
        bot._parse_ref("famous alumni")
