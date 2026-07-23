"""Discord gateway bot: 🎫 reaction on a support-forum thread -> Jira ticket.

Trigger: the thread author or a member with a configured team role reacts
with the ticket emoji on any message in a thread under the configured forum
channel. The bot replies in the thread with the issue link.

Dedup is stateless: before creating, the bot searches Jira for the
discord-thread-<id> label. Jira's search index is eventually consistent, so
two reactions seconds apart *can* produce a duplicate ticket — accepted
trade-off for not managing local state.
"""

import asyncio
import logging
from collections import defaultdict

import discord

import config
import transcript
from jira_client import JiraClient, JiraError

log = logging.getLogger("discord-jira-support")

HISTORY_LIMIT = 200

intents = discord.Intents.none()
intents.guilds = True
intents.guild_reactions = True
intents.message_content = True  # privileged: enable in the Developer Portal

bot = discord.Client(intents=intents)
jira = JiraClient(config.JIRA_BASE_URL, config.JIRA_EMAIL, config.JIRA_API_TOKEN,
                  browse_base_url=config.JIRA_BROWSE_BASE_URL)

# Serializes check->create for near-simultaneous reactions within this
# process; across restarts/instances the Jira label search is the (eventually
# consistent) guard.
_thread_locks = defaultdict(asyncio.Lock)


def _is_ticket_emoji(emoji: discord.PartialEmoji) -> bool:
    name = (emoji.name or "").rstrip("\ufe0f")
    if emoji.is_unicode_emoji():
        return name in config.TICKET_EMOJIS
    # Custom server emojis match by short name, e.g. :ticket:
    return name.lower() in config.TICKET_EMOJI_NAMES


@bot.event
async def on_ready():
    log.info("Logged in as %s (id %s), watching forum channel %s",
             bot.user, bot.user.id, config.DISCORD_FORUM_CHANNEL_ID)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if not _is_ticket_emoji(payload.emoji):
        return
    if payload.user_id == bot.user.id or (payload.member and payload.member.bot):
        return

    thread = bot.get_channel(payload.channel_id)
    if thread is None:
        try:
            thread = await bot.fetch_channel(payload.channel_id)
        except discord.HTTPException:
            return
    if not (isinstance(thread, discord.Thread)
            and thread.parent_id == config.DISCORD_FORUM_CHANNEL_ID):
        return

    authorized = payload.user_id == thread.owner_id or (
        payload.member
        and any(role.id in config.DISCORD_TEAM_ROLE_IDS for role in payload.member.roles)
    )
    if not authorized:
        log.debug("Ignoring unauthorized 🎫 from user %s in thread %s",
                  payload.user_id, thread.id)
        return

    async with _thread_locks[thread.id]:
        await handle_ticket_request(thread, payload.user_id)


async def handle_ticket_request(thread: discord.Thread, requester_id: int):
    thread_label = f"discord-thread-{thread.id}"
    try:
        existing = await asyncio.to_thread(jira.find_issue_by_label, thread_label)
        if existing:
            await reply_in_thread(thread, existing[0], existing[1],
                                  already_existed=True)
            return

        messages = await fetch_thread_messages(thread)
        transcript_text = build_transcript_text(messages)
        summary = thread.name or f"Discord support thread {thread.id}"
        issue_key, issue_url = await asyncio.to_thread(
            jira.create_request, config.JIRA_SERVICE_DESK_ID,
            config.JIRA_REQUEST_TYPE_ID, summary,
            f"Discord thread: {thread.jump_url}\n\n{transcript_text}",
        )
    except JiraError as exc:
        log.error("Jira request failed for thread %s: %s", thread.id, exc)
        await send_safely(thread, content=(
            "Couldn't create a Jira ticket for this thread "
            f"(Jira responded with {exc.status}). Ask an admin to check the bot logs."
        ))
        return
    except Exception:
        log.exception("Unexpected failure for thread %s", thread.id)
        return

    # The request form doesn't accept labels or ADF, so enrich after creation.
    # The dedup label matters most; if this fails the ticket still exists but
    # a re-react could duplicate it, so log loudly.
    try:
        description = build_description(thread, messages, transcript_text)
        await asyncio.to_thread(
            jira.update_issue, issue_key, description,
            config.JIRA_EXTRA_LABELS + [thread_label],
        )
    except JiraError as exc:
        log.error("Created %s but failed to set labels/description: %s",
                  issue_key, exc)

    log.info("Created %s for thread %s (%r)", issue_key, thread.id, thread.name)
    await reply_in_thread(thread, issue_key, issue_url, already_existed=False,
                          requester_id=requester_id)


async def fetch_thread_messages(thread: discord.Thread) -> list:
    # In forum threads the starter message lives inside the thread (its ID ==
    # thread ID), so history() alone covers it.
    messages = []
    async for m in thread.history(limit=HISTORY_LIMIT, oldest_first=True):
        if m.type not in (discord.MessageType.default, discord.MessageType.reply):
            continue
        messages.append(m)
    return messages


def build_transcript_text(messages: list) -> str:
    formatted = [
        transcript.FormattedMsg(text=transcript.format_message(
            m.author.display_name, m.created_at, m.content,
            [a.url for a in m.attachments],
        ))
        for m in messages
    ]
    return transcript.build_transcript(formatted)


def build_description(thread: discord.Thread, messages: list,
                      transcript_text: str) -> dict:
    author_name = str(messages[0].author.display_name) if messages else f"user {thread.owner_id}"
    return transcript.build_description_adf(
        thread_name=thread.name,
        thread_url=thread.jump_url,
        author_name=author_name,
        created_at=thread.created_at,
        message_count=len(messages),
        transcript_text=transcript_text,
    )


async def reply_in_thread(thread: discord.Thread, issue_key: str, issue_url: str,
                          already_existed: bool, requester_id: int | None = None):
    contact = f"Contact {config.SUPPORT_EMAIL} for updates on this ticket."
    if already_existed:
        embed = discord.Embed(
            description=(f"A support ticket already exists for this thread: "
                         f"**{issue_key}**\n{contact}"),
            color=discord.Color.greyple(),
        )
    else:
        embed = discord.Embed(
            title=f"Support ticket created: {issue_key}",
            description=contact,
            color=discord.Color.green(),
        )
        if requester_id:
            embed.set_footer(text="requested via 🎫 reaction")
    await send_safely(thread, embed=embed)


async def send_safely(thread: discord.Thread, **kwargs):
    """Send to the thread, unarchiving once if the first attempt fails."""
    try:
        await thread.send(**kwargs)
    except discord.HTTPException:
        try:
            await thread.edit(archived=False, locked=False)
            await thread.send(**kwargs)
        except discord.HTTPException:
            log.exception("Could not reply in thread %s", thread.id)


def main():
    config.validate()
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bot.run(config.DISCORD_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
