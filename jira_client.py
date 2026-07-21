"""Minimal Jira Cloud client — just what the bot needs.

Tickets are created through the Service Management API
(/rest/servicedeskapi/request) so they get a request type, show up in agent
queues, and start SLAs like any other support request. Labels and the rich
ADF description aren't settable on request creation, so they're applied with
a follow-up edit through the regular issue API.

Synchronous on purpose; bot.py calls it via asyncio.to_thread so the
gateway heartbeat is never blocked.
"""

import time

import requests
from requests.auth import HTTPBasicAuth

MAX_SUMMARY_CHARS = 255
TIMEOUT_SECONDS = 30


class JiraError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        super().__init__(f"Jira API error {status}: {detail}")


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(email, api_token)
        self._session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )

    def create_request(self, service_desk_id: str, request_type_id: str,
                       summary: str, description_text: str) -> tuple:
        """Create a JSM customer request; returns (issue_key, browse_url)."""
        payload = {
            "serviceDeskId": service_desk_id,
            "requestTypeId": request_type_id,
            "requestFieldValues": {
                "summary": summary[:MAX_SUMMARY_CHARS],
                "description": description_text,
            },
        }
        resp = self._post_with_retry(
            f"{self.base_url}/rest/servicedeskapi/request", payload)
        key = resp.json()["issueKey"]
        return key, f"{self.base_url}/browse/{key}"

    def update_issue(self, issue_key: str, description_adf: dict,
                     labels: list) -> None:
        resp = self._session.put(
            f"{self.base_url}/rest/api/3/issue/{issue_key}",
            json={"fields": {"description": description_adf, "labels": labels}},
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            raise JiraError(resp.status_code, _error_detail(resp))

    def find_issue_by_label(self, label: str):
        """Return (issue_key, browse_url) of the first issue with this label,
        or None. Jira's search index is eventually consistent, so a just-created
        issue may not be found — acceptable rare-duplicate window."""
        resp = self._session.get(
            f"{self.base_url}/rest/api/3/search/jql",
            params={"jql": f'labels = "{label}"', "fields": "key", "maxResults": 1},
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            raise JiraError(resp.status_code, _error_detail(resp))
        issues = resp.json().get("issues", [])
        if not issues:
            return None
        key = issues[0]["key"]
        return key, f"{self.base_url}/browse/{key}"

    def _post_with_retry(self, url: str, payload: dict):
        resp = self._session.post(url, json=payload, timeout=TIMEOUT_SECONDS)
        if resp.status_code == 429:
            time.sleep(float(resp.headers.get("Retry-After", "5")))
            resp = self._session.post(url, json=payload, timeout=TIMEOUT_SECONDS)
        if resp.status_code >= 400:
            raise JiraError(resp.status_code, _error_detail(resp))
        return resp


def _error_detail(resp) -> str:
    if resp.status_code == 401:
        return "authentication failed (check JIRA_EMAIL / JIRA_API_TOKEN)"
    if resp.status_code == 403:
        return "permission denied (service account can't create issues in this project)"
    try:
        body = resp.json()
    except ValueError:
        return "unparseable error response"
    parts = list(body.get("errorMessages", []))
    parts += [f"{field}: {msg}" for field, msg in body.get("errors", {}).items()]
    return "; ".join(parts) or "no detail provided"
