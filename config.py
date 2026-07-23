"""Central configuration: environment variables and paths. Loaded once at
import; call validate() at startup to fail fast on missing required vars."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent
load_dotenv(REPO_ROOT / ".env")


def _int_or_zero(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_FORUM_CHANNEL_ID = _int_or_zero(os.environ.get("DISCORD_FORUM_CHANNEL_ID", "0"))
DISCORD_TEAM_ROLE_IDS = frozenset(
    _int_or_zero(part)
    for part in os.environ.get("DISCORD_TEAM_ROLE_IDS", "").split(",")
    if part.strip()
)

JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
# Human-facing /browse links; set when JIRA_BASE_URL is the api.atlassian.com
# gateway (service-account tokens). Defaults to JIRA_BASE_URL.
JIRA_BROWSE_BASE_URL = os.environ.get("JIRA_BROWSE_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
JIRA_SERVICE_DESK_ID = os.environ.get("JIRA_SERVICE_DESK_ID", "")
JIRA_REQUEST_TYPE_ID = os.environ.get("JIRA_REQUEST_TYPE_ID", "")
JIRA_EXTRA_LABELS = [
    label.strip()
    for label in os.environ.get("JIRA_EXTRA_LABELS", "discord-support").split(",")
    if label.strip()
]

# 🎫 (:ticket:) and 🎟️ (:tickets:) look nearly identical in the picker, so
# accept both by default. Comparison strips the U+FE0F variation selector.
TICKET_EMOJIS = frozenset(
    e.strip().rstrip("\ufe0f")
    for e in os.environ.get("TICKET_EMOJIS", "🎫,🎟️").split(",")
    if e.strip()
)
# Custom server emojis that also trigger, matched by short name
TICKET_EMOJI_NAMES = frozenset(
    n.strip().lower()
    for n in os.environ.get("TICKET_EMOJI_NAMES", "ticket,tickets").split(",")
    if n.strip()
)
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@tenstorrent.com")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

_REQUIRED = [
    "DISCORD_BOT_TOKEN",
    "DISCORD_FORUM_CHANNEL_ID",
    "JIRA_BASE_URL",
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "JIRA_SERVICE_DESK_ID",
    "JIRA_REQUEST_TYPE_ID",
]


def validate() -> None:
    missing = [name for name in _REQUIRED if not globals()[name]]
    if missing:
        sys.exit(f"Missing required environment variables: {', '.join(missing)}")
