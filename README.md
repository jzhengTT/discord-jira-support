# discord-jira-support

Discord gateway bot that turns support-forum threads into Jira tickets.

When the **thread author** or a member with a configured **team role** reacts
with 🎫 on any message in a thread of the configured forum channel, the bot:

1. Creates a **Jira Service Management customer request** (via
   `/rest/servicedeskapi/request`) so Discord tickets behave like every other
   support request — proper request type, agent queues, SLAs, resolution
   automation. Thread title becomes the summary; the description gets a
   transcript snapshot (capped ~30k chars) and a permalink back to the thread;
   labels `discord-support` + `discord-thread-<id>` are applied with a
   follow-up edit (the request form doesn't accept labels).
2. Replies in the thread with the ticket number and a note to contact
   `SUPPORT_EMAIL` for updates (the Jira link is agent-only, so it isn't
   posted publicly).

One ticket per thread: before creating, the bot searches Jira for the
`discord-thread-<id>` label and replies with the existing ticket if found. The
bot is fully stateless — nothing to persist across restarts. Caveat: Jira's
search index is eventually consistent, so two reactions within a few seconds
of each other can rarely produce a duplicate ticket (the in-process lock
prevents this for a single running bot; it can happen across restarts or
multiple instances).

## Setup

### 1. Discord application

1. [Developer Portal](https://discord.com/developers/applications) → New
   Application → **Bot**.
2. Under *Bot*, enable the **Message Content Intent** (privileged — required to
   read thread messages for the transcript). Copy the bot token.
3. Invite the bot via *OAuth2 → URL Generator*: scope `bot`, permissions
   **View Channels, Read Message History, Send Messages, Send Messages in
   Threads, Add Reactions, Manage Threads** (Manage Threads is only needed to
   unarchive locked threads before replying).
4. Enable Developer Mode in your Discord client, then right-click → *Copy ID*
   on the support forum channel and the team role(s).

### 2. Jira service account

1. Create an API token for the service account at
   <https://id.atlassian.com/manage-profile/security/api-tokens>.
2. The account needs **agent access** to the service desk project (to create
   requests and edit issues for the labels/description follow-up).

   **Atlassian service accounts** (created in admin.atlassian.com, [docs](https://support.atlassian.com/user-management/docs/manage-api-tokens-for-service-accounts/))
   must call the platform gateway instead of the site URL. Same Basic auth,
   different base URL:

   ```sh
   JIRA_BASE_URL=https://api.atlassian.com/ex/jira/<cloud-id>
   JIRA_BROWSE_BASE_URL=https://tenstorrent.atlassian.net
   ```
3. Find the service desk and request type IDs if they differ from the
   defaults: `GET /rest/servicedeskapi/servicedesk` lists desks,
   `GET /rest/servicedeskapi/servicedesk/{id}/requesttype` lists request
   types. For Tenstorrent's CUST project: service desk `1`, request type
   `108` ("General Support").

### 3. Configure and run

```sh
cp .env.example .env   # fill in tokens and IDs
docker compose up -d --build
```

Or locally without Docker:

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python bot.py
```

## Configuration

| Variable | Required | Meaning |
|---|---|---|
| `DISCORD_BOT_TOKEN` | yes | Bot token from the Developer Portal |
| `DISCORD_FORUM_CHANNEL_ID` | yes | The forum channel to watch |
| `DISCORD_TEAM_ROLE_IDS` | no | Comma-separated role IDs that may trigger tickets (besides the thread author) |
| `JIRA_BASE_URL` | yes | Site URL, or `https://api.atlassian.com/ex/jira/<cloud-id>` for service-account tokens |
| `JIRA_BROWSE_BASE_URL` | no | Site URL for human-facing links when `JIRA_BASE_URL` is the api.atlassian.com gateway |
| `JIRA_EMAIL` / `JIRA_API_TOKEN` | yes | Service-account credentials (agent) |
| `JIRA_SERVICE_DESK_ID` | yes | JSM service desk ID (CUST = `1`) |
| `JIRA_REQUEST_TYPE_ID` | yes | Request type ID (CUST "General Support" = `108`) |
| `JIRA_EXTRA_LABELS` | no | Comma-separated, default `discord-support` |
| `TICKET_EMOJI` | no | Default 🎫 (unicode only) |
| `SUPPORT_EMAIL` | no | Shown in the Discord reply, default `support@tenstorrent.com` |
| `LOG_LEVEL` | no | Default `INFO` |

## Tests

```sh
.venv/bin/python -m pytest
```

## Manual end-to-end verification

In a test server with a forum channel (and a sandbox Jira project):

- React 🎫 as the thread author → ticket created, green embed reply.
- React 🎫 again (after a few seconds) → grey "already exists" reply, no
  second ticket.
- React as a non-author without the team role → nothing happens.
- React as a team-role holder on someone else's thread → works.
- Archive the thread, then react → reply lands and the thread unarchives.
- Restart the bot, react 🎫 on the same thread again → still finds the
  existing ticket via the Jira label search.
