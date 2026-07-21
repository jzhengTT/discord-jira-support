"""Pure formatting: Discord thread messages -> transcript text -> ADF doc.

No discord.py imports here so everything is unit-testable; bot.py adapts
discord.Message objects into FormattedMsg via format_message().
"""

from dataclasses import dataclass
from datetime import datetime

MAX_TRANSCRIPT_CHARS = 30_000  # headroom under Jira's ~32k practical limit
HEAD_MESSAGES = 30
TAIL_MESSAGES = 20
OMITTED_MARKER = "\n\n…… {n} messages omitted ……\n\n"
TRUNCATED_MARKER = "… [truncated]"


@dataclass(frozen=True)
class FormattedMsg:
    text: str


def format_message(author_name: str, created_at: datetime, content: str,
                   attachment_urls: list) -> str:
    stamp = created_at.strftime("%Y-%m-%d %H:%M UTC")
    line = f"[{stamp}] {author_name}: {content}"
    for url in attachment_urls:
        line += f"\n  [attachment] {url}"
    return line


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(TRUNCATED_MARKER)] + TRUNCATED_MARKER


def _cap_keeping_end(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return TRUNCATED_MARKER + text[-(limit - len(TRUNCATED_MARKER)):]


def build_transcript(messages: list) -> str:
    full = "\n".join(m.text for m in messages)
    if len(full) <= MAX_TRANSCRIPT_CHARS:
        return full

    omitted = len(messages) - HEAD_MESSAGES - TAIL_MESSAGES
    if omitted > 0:
        head = "\n".join(m.text for m in messages[:HEAD_MESSAGES])
        tail = "\n".join(m.text for m in messages[-TAIL_MESSAGES:])
        marker = OMITTED_MARKER.format(n=omitted)
        budget = MAX_TRANSCRIPT_CHARS - len(marker)
        # Even head+tail can blow the cap if messages are huge; split the
        # budget so the result always fits.
        head = _cap(head, budget // 2)
        tail = _cap_keeping_end(tail, budget - len(head))
        return head + marker + tail

    # Few messages but still over the cap: some message is giant.
    return _cap(full, MAX_TRANSCRIPT_CHARS)


def build_description_adf(thread_name: str, thread_url: str, author_name: str,
                          created_at: datetime, message_count: int,
                          transcript_text: str) -> dict:
    stamp = created_at.strftime("%Y-%m-%d %H:%M UTC")
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Discord thread: "},
                    {
                        "type": "text",
                        "text": thread_name,
                        "marks": [{"type": "link", "attrs": {"href": thread_url}}],
                    },
                ],
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Opened by {author_name} on {stamp} · "
                            f"{message_count} messages at ticket creation"
                        ),
                    },
                ],
            },
            {
                "type": "codeBlock",
                "attrs": {},
                "content": [{"type": "text", "text": transcript_text}],
            },
        ],
    }
