"""Discord bot for reviewing each day's prompts and answer lists before they go live.

    python -m rarest_blue.entrypoints.discord_bot

Every night after the generator runs it posts the new set to the review channel; /review posts any stored day on
demand. Reviewers suggest fixes with slash commands, the bot checks each one against the whole day the way
`prompts.sh check` does, and posts it with an Apply button for anyone with the reviewer role (or Manage Server).

The posts show every answer, so keep the review channel private. Needs DATABASE_URL and the DISCORD_* settings in
config.py; see supabase/README.md for setting up the Discord app.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import Callable
from datetime import date, time, timedelta
from typing import TypeVar

import discord
from discord import app_commands
from discord.ext import tasks

from ..application import editing
from ..application.editing import Change
from ..application.ports import UnitOfWork
from ..config import Settings
from ..domain import days
from ..domain.models import Prompt
from ..domain.rules import TORONTO
from ..infrastructure import postgres

log = logging.getLogger(__name__)
T = TypeVar("T")

# The generator runs at 23:30 and writes the set for two days out; give it time to finish (and retry once).
AUTO_POST_AT = time(23, 50, tzinfo=TORONTO)
GENERATED_DAYS_AHEAD = 2
# Discord's limits: embed description, field value, autocomplete choices and choice names.
DESCRIPTION_LIMIT = 4096
FIELD_LIMIT = 1024
FOOTER_LIMIT = 2048
MESSAGE_LIMIT = 2000
MAX_CHOICES = 25
CHOICE_NAME_LIMIT = 100
# The suggestion's change rides in its embed footer, so Apply still works after the bot restarts.
FOOTER_TAG = "change:"
APPLIED, DISMISSED, PENDING = discord.Color.green(), discord.Color.dark_grey(), discord.Color.blurple()


class ReviewBot(discord.Client):
    def __init__(self, settings: Settings):
        super().__init__(intents=discord.Intents.default())
        self.settings = settings
        self.tree = app_commands.CommandTree(self)
        # One database call at a time: reviewers are few, and it keeps two Apply clicks from racing on one prompt.
        self._db_lock = asyncio.Lock()

    async def db(self, fn: Callable[..., T], *args) -> T:
        """Run fn(uow, *args) in one transaction, off the event loop."""
        async with self._db_lock:
            return await asyncio.to_thread(self._in_transaction, fn, *args)

    def _in_transaction(self, fn: Callable[..., T], *args) -> T:
        with postgres.PostgresUnitOfWork(self.settings.database_url) as uow:
            return fn(uow, *args)

    async def setup_hook(self) -> None:
        self.add_view(SuggestionView(self))
        guild = discord.Object(id=self.settings.discord_guild_id)
        _register_commands(self, guild)
        await self.tree.sync(guild=guild)
        self.nightly_post.start()

    async def on_ready(self) -> None:
        log.info("logged in as %s; reviewing in channel %s", self.user, self.settings.discord_review_channel_id)

    @tasks.loop(time=AUTO_POST_AT)
    async def nightly_post(self) -> None:
        channel = self.get_channel(self.settings.discord_review_channel_id)
        if not isinstance(channel, discord.TextChannel):
            log.error("review channel %s not found", self.settings.discord_review_channel_id)
            return
        day = days.today() + timedelta(days=GENERATED_DAYS_AHEAD)
        await post_set(self, channel, day)

    def can_apply(self, user: discord.abc.User) -> bool:
        if not isinstance(user, discord.Member):
            return False
        return user.guild_permissions.manage_guild or any(
            r.id == self.settings.discord_reviewer_role_id for r in user.roles
        )


# --- Posting a day's set -------------------------------------------------------------------------------------------


def _prompts(uow: UnitOfWork, day: date) -> list[Prompt] | None:
    return uow.prompts.get(day)


async def post_set(bot: ReviewBot, channel: discord.abc.Messageable, day: date) -> None:
    prompts = await bot.db(_prompts, day)
    if prompts is None:
        await channel.send(f"No stored set for **{_label(day)}** yet. (The nightly generator may have failed.)")
        return
    await channel.send(
        f"## Set for {_label(day)}\n"
        f"Goes live at midnight on {_label(day)}. Until then any fix can go in; after that, only new answers and "
        "aliases. Suggest fixes with `/add-answer`, `/add-alias`, `/remove-answer`, `/remove-decoy` and `/set-golden`."
    )
    for n, prompt in enumerate(prompts, 1):
        await channel.send(embed=prompt_embed(day, n, prompt))


def prompt_embed(day: date, n: int, p: Prompt) -> discord.Embed:
    lines = []
    for i, names in enumerate(p.answers, 1):
        line = f"{i}. **{names[0]}**"
        if len(names) > 1:
            line += f" · {', '.join(names[1:])}"
        if names[0] == p.golden:
            line += " ⭐"
            if p.golden_why:
                line += f"\n  ↳ *{p.golden_why}*"
        lines.append(line)
    embed = discord.Embed(
        title=f"{n}. {p.text}"[:256],
        description=_fit([f"*Hint: {p.hint}*", ""] + lines, DESCRIPTION_LIMIT),
        color=PENDING,
    )
    if p.decoys:
        embed.add_field(name="Decoys (wrong on purpose)", value=_fit([", ".join(p.decoys)], FIELD_LIMIT), inline=False)
    embed.set_footer(text=f"{day.isoformat()} · {p.id} · {len(p.answers)} answers")
    return embed


def _fit(lines: list[str], limit: int) -> str:
    """Join lines, cutting off whole lines (with a count of what's missing) to stay under Discord's limit."""
    out = "\n".join(lines)
    if len(out) <= limit:
        return out
    kept = []
    for i, line in enumerate(lines):
        more = f"\n…and {len(lines) - i} more lines"
        if len("\n".join([*kept, line])) + len(more) > limit:
            return "\n".join(kept) + more
        kept.append(line)
    return out


def _label(day: date) -> str:
    return day.strftime("%a %b %-d")


# --- Suggestions ---------------------------------------------------------------------------------------------------


def describe(change: Change, prompt: Prompt) -> str:
    match change.kind:
        case "add_answer":
            aliases = f" (also accepts: {', '.join(change.aliases)})" if change.aliases else ""
            return f"Add answer **{change.name}**{aliases} to *{prompt.text}*"
        case "add_alias":
            return f"Accept **{change.text}** as **{change.name}** for *{prompt.text}*"
        case "remove_answer":
            return f"Remove answer **{change.name}** from *{prompt.text}*"
        case "remove_decoy":
            return f"Remove decoy **{change.name}** from *{prompt.text}* (it'll stop showing in autocomplete)"
        case "set_golden":
            why = f"\n↳ *{change.text}*" if change.text else ""
            return f"Make **{change.name}** the golden answer for *{prompt.text}*{why}"
    return change.kind


def _preview(uow: UnitOfWork, day: date, change: Change) -> tuple[Prompt, editing.Report, bool]:
    today = days.today()
    updated, report = editing.preview_change(uow, day, today, change)
    return updated, report, editing.is_live(uow, day, today)


def _commit(uow: UnitOfWork, day: date, change: Change) -> int:
    return editing.commit_change(uow, day, days.today(), change)


async def suggest(bot: ReviewBot, interaction: discord.Interaction, prompt_ref: str, change_for: Callable) -> None:
    """Check a suggested change against the whole day and post it with Apply/Dismiss, or tell the reviewer why not."""
    if not await _in_review_channel(bot, interaction):
        return
    try:
        day, prompt_id = _parse_ref(prompt_ref)
        change = change_for(prompt_id)
        updated, report, live = await bot.db(_preview, day, change)
    except ValueError as e:
        await interaction.response.send_message(f"Can't suggest that: {e}", ephemeral=True)
        return
    if not report.ok:
        await interaction.response.send_message(
            _fit(["Can't suggest that, it would break the day:", *(f"- {e}" for e in report.errors)], MESSAGE_LIMIT),
            ephemeral=True,
        )
        return

    embed = discord.Embed(title=f"Suggestion for {_label(day)}", description=describe(change, updated), color=PENDING)
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    if live:
        embed.add_field(name="Live day", value="Applying it rescores every player who typed this.", inline=False)
    warnings = [w for w in report.warnings if w.startswith(f"{prompt_id}:")]
    if warnings:
        embed.add_field(name="Warnings", value=_fit([f"- {w}" for w in warnings], FIELD_LIMIT), inline=False)
    data = {"day": day.isoformat(), "by": interaction.user.id, **change.to_dict()}
    footer = FOOTER_TAG + json.dumps(data, ensure_ascii=False)
    if len(footer) > FOOTER_LIMIT:
        await interaction.response.send_message("That's too long to suggest; shorten it.", ephemeral=True)
        return
    embed.set_footer(text=footer)
    await interaction.response.send_message(embed=embed, view=SuggestionView(bot))


class SuggestionView(discord.ui.View):
    """Apply/Dismiss buttons. Fixed custom ids and no timeout, so buttons on old messages keep working."""

    def __init__(self, bot: ReviewBot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Apply", style=discord.ButtonStyle.success, custom_id="rarest_blue:apply")
    async def apply(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        if not self.bot.can_apply(interaction.user):
            await interaction.response.send_message("Only reviewers can apply suggestions.", ephemeral=True)
            return
        embed, day, change, _ = _from_message(interaction.message)
        try:
            rescored = await self.bot.db(_commit, day, change)
        except ValueError as e:
            # Most likely the set changed since the suggestion (or the day went live); the buttons stay.
            await interaction.response.send_message(f"Couldn't apply it: {e}", ephemeral=True)
            return
        done = f"Applied by {interaction.user.mention}"
        if rescored:
            done += f", rescored {rescored} guesses"
        embed.color = APPLIED
        embed.add_field(name="Done", value=done, inline=False)
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.secondary, custom_id="rarest_blue:dismiss")
    async def dismiss(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        embed, _, _, suggester = _from_message(interaction.message)
        if not (self.bot.can_apply(interaction.user) or interaction.user.id == suggester):
            await interaction.response.send_message("Only reviewers or the suggester can dismiss it.", ephemeral=True)
            return
        embed.color = DISMISSED
        embed.add_field(name="Dismissed", value=f"by {interaction.user.mention}", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)


def _from_message(message: discord.Message | None) -> tuple[discord.Embed, date, Change, int]:
    """The suggestion's embed, day, change and suggester's user id."""
    embed = message.embeds[0]
    data = json.loads(embed.footer.text.removeprefix(FOOTER_TAG))
    return embed, date.fromisoformat(data["day"]), Change.from_dict(data), data["by"]


# --- Slash commands ------------------------------------------------------------------------------------------------


def _parse_ref(ref: str) -> tuple[date, str]:
    """Prompt options are "YYYY-MM-DD/prompt_id", so one option picks both the day and the prompt."""
    day, _, prompt_id = ref.partition("/")
    try:
        return date.fromisoformat(day), prompt_id
    except ValueError:
        raise ValueError("pick a prompt from the list") from None


def _reviewable(uow: UnitOfWork) -> list[tuple[date, list[Prompt]]]:
    """Stored sets from today (live: additions only) through the newest generated day."""
    today = days.today()
    found = []
    for ahead in range(GENERATED_DAYS_AHEAD + 1):
        day = today + timedelta(days=ahead)
        if (prompts := uow.prompts.get(day)) is not None:
            found.append((day, prompts))
    return found


async def _in_review_channel(bot: ReviewBot, interaction: discord.Interaction) -> bool:
    if interaction.channel_id == bot.settings.discord_review_channel_id:
        return True
    where = f"<#{bot.settings.discord_review_channel_id}>"
    await interaction.response.send_message(
        f"Use this in {where}, so answers stay out of public channels.", ephemeral=True
    )
    return False


def _choices(pairs: list[tuple[str, str]], current: str) -> list[app_commands.Choice[str]]:
    key = current.casefold()
    return [
        app_commands.Choice(name=name[:CHOICE_NAME_LIMIT], value=value)
        for name, value in pairs
        if key in name.casefold()
    ][:MAX_CHOICES]


def _register_commands(bot: ReviewBot, guild: discord.Object) -> None:
    tree = bot.tree

    async def prompt_choices(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if interaction.channel_id != bot.settings.discord_review_channel_id:
            return []
        sets = await bot.db(_reviewable)
        pairs = [(f"{_label(day)} · {p.text}", f"{day.isoformat()}/{p.id}") for day, prompts in sets for p in prompts]
        return _choices(pairs, current)

    def names_of(pick: Callable[[Prompt], list[str]]):
        async def complete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
            if interaction.channel_id != bot.settings.discord_review_channel_id:
                return []
            try:
                day, prompt_id = _parse_ref(interaction.namespace.prompt or "")
            except ValueError:
                return []
            prompts = await bot.db(_prompts, day) or []
            prompt = next((p for p in prompts if p.id == prompt_id), None)
            return _choices([(n, n) for n in pick(prompt)], current) if prompt else []

        return complete

    answers = names_of(lambda p: p.canonical_answers)
    decoys = names_of(lambda p: list(p.decoys))

    @tree.command(name="review", description="Post a day's prompts and answer lists", guild=guild)
    @app_commands.describe(day="Day to post (default: the newest stored set)")
    async def review_cmd(interaction: discord.Interaction, day: str | None = None) -> None:
        if not await _in_review_channel(bot, interaction):
            return
        sets = await bot.db(_reviewable)
        try:
            target = date.fromisoformat(day) if day else (sets[-1][0] if sets else days.today())
        except ValueError:
            await interaction.response.send_message("Give the day as YYYY-MM-DD.", ephemeral=True)
            return
        await interaction.response.send_message(f"Posting {_label(target)}…", ephemeral=True)
        await post_set(bot, interaction.channel, target)

    @review_cmd.autocomplete("day")
    async def review_days(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        sets = await bot.db(_reviewable)
        return _choices([(f"{_label(d)} ({d.isoformat()})", d.isoformat()) for d, _ in sets], current)

    @tree.command(name="add-answer", description="Suggest a correct answer the list is missing", guild=guild)
    @app_commands.describe(
        prompt="Which prompt", answer="The answer as it should be shown", aliases="Other spellings, comma-separated"
    )
    @app_commands.autocomplete(prompt=prompt_choices)
    async def add_answer(interaction: discord.Interaction, prompt: str, answer: str, aliases: str = "") -> None:
        extra = tuple(a.strip() for a in aliases.split(",") if a.strip())
        await suggest(bot, interaction, prompt, lambda pid: Change("add_answer", pid, answer, aliases=extra))

    @tree.command(name="add-alias", description="Suggest another spelling or nickname for an answer", guild=guild)
    @app_commands.describe(prompt="Which prompt", answer="The existing answer", alias="What players might type")
    @app_commands.autocomplete(prompt=prompt_choices, answer=answers)
    async def add_alias(interaction: discord.Interaction, prompt: str, answer: str, alias: str) -> None:
        await suggest(bot, interaction, prompt, lambda pid: Change("add_alias", pid, answer, text=alias))

    @tree.command(name="remove-answer", description="Suggest removing a wrong answer", guild=guild)
    @app_commands.describe(prompt="Which prompt", answer="The answer to remove")
    @app_commands.autocomplete(prompt=prompt_choices, answer=answers)
    async def remove_answer(interaction: discord.Interaction, prompt: str, answer: str) -> None:
        await suggest(bot, interaction, prompt, lambda pid: Change("remove_answer", pid, answer))

    @tree.command(name="remove-decoy", description="Suggest removing a decoy that's actually right", guild=guild)
    @app_commands.describe(prompt="Which prompt", decoy="The decoy to remove (use /add-answer if it should score)")
    @app_commands.autocomplete(prompt=prompt_choices, decoy=decoys)
    async def remove_decoy(interaction: discord.Interaction, prompt: str, decoy: str) -> None:
        await suggest(bot, interaction, prompt, lambda pid: Change("remove_decoy", pid, decoy))

    @tree.command(
        name="set-golden", description="Suggest a different golden answer, or a better explanation", guild=guild
    )
    @app_commands.describe(prompt="Which prompt", answer="The new golden answer", why="One line on why it's a deep cut")
    @app_commands.autocomplete(prompt=prompt_choices, answer=answers)
    async def set_golden(interaction: discord.Interaction, prompt: str, answer: str, why: str = "") -> None:
        await suggest(bot, interaction, prompt, lambda pid: Change("set_golden", pid, answer, text=why))


def main(settings: Settings | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    settings = settings or Settings.from_env()
    missing = [
        name
        for name, value in [
            ("DISCORD_BOT_TOKEN", settings.discord_bot_token),
            ("DISCORD_GUILD_ID", settings.discord_guild_id),
            ("DISCORD_REVIEW_CHANNEL_ID", settings.discord_review_channel_id),
        ]
        if not value
    ]
    if missing:
        print(f"set {', '.join(missing)} first (see supabase/README.md)", file=sys.stderr)
        return 1
    if not settings.discord_reviewer_role_id:
        log.warning("DISCORD_REVIEWER_ROLE_ID is unset, so only members with Manage Server can apply suggestions")
    ReviewBot(settings).run(settings.discord_bot_token, log_handler=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
