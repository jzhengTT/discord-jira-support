import pytest

from jira_client import JiraClient, JiraError


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    """Stands in for requests.Session; records calls, replays queued responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"method": "post", "url": url, "json": json})
        return self.responses.pop(0)

    def put(self, url, json=None, timeout=None):
        self.calls.append({"method": "put", "url": url, "json": json})
        return self.responses.pop(0)

    def get(self, url, params=None, timeout=None):
        self.calls.append({"method": "get", "url": url, "params": params})
        return self.responses.pop(0)


ADF = {"type": "doc", "version": 1, "content": []}


def make_client(responses, **kwargs):
    client = JiraClient("https://x.atlassian.net", "svc@example.com", "tok", **kwargs)
    fake = FakeSession(responses)
    client._session = fake
    return client, fake


def test_browse_url_uses_browse_base_when_configured():
    client, fake = make_client(
        [FakeResponse(201, {"issueKey": "CUST-5"})],
        browse_base_url="https://x.atlassian.net",
    )
    client.base_url = "https://api.atlassian.com/ex/jira/abc123"

    key, url = client.create_request(service_desk_id="1", request_type_id="108",
                                     summary="s", description_text="d")

    assert fake.calls[0]["url"].startswith("https://api.atlassian.com/ex/jira/abc123/")
    assert url == "https://x.atlassian.net/browse/CUST-5"


def test_browse_url_defaults_to_base_url():
    client, _ = make_client([FakeResponse(201, {"issueKey": "CUST-5"})])

    _, url = client.create_request(service_desk_id="1", request_type_id="108",
                                   summary="s", description_text="d")

    assert url == "https://x.atlassian.net/browse/CUST-5"


def test_create_request_returns_key_and_browse_url():
    client, fake = make_client([FakeResponse(201, {"issueKey": "CUST-900"})])

    key, url = client.create_request(
        service_desk_id="1", request_type_id="108",
        summary="Board won't boot", description_text="plain transcript",
    )

    assert key == "CUST-900"
    assert url == "https://x.atlassian.net/browse/CUST-900"


def test_create_request_payload_shape():
    client, fake = make_client([FakeResponse(201, {"issueKey": "CUST-1"})])

    client.create_request(service_desk_id="1", request_type_id="108",
                          summary="s", description_text="d")

    call = fake.calls[0]
    assert call["url"] == "https://x.atlassian.net/rest/servicedeskapi/request"
    assert call["json"] == {
        "serviceDeskId": "1",
        "requestTypeId": "108",
        "requestFieldValues": {"summary": "s", "description": "d"},
    }


def test_create_request_summary_truncated_to_255_chars():
    client, fake = make_client([FakeResponse(201, {"issueKey": "CUST-1"})])

    client.create_request(service_desk_id="1", request_type_id="108",
                          summary="z" * 300, description_text="d")

    assert len(fake.calls[0]["json"]["requestFieldValues"]["summary"]) == 255


def test_update_issue_puts_description_and_labels():
    client, fake = make_client([FakeResponse(204)])

    client.update_issue("CUST-900", description_adf=ADF,
                        labels=["discord-support", "discord-thread-123"])

    call = fake.calls[0]
    assert call["method"] == "put"
    assert call["url"] == "https://x.atlassian.net/rest/api/3/issue/CUST-900"
    assert call["json"]["fields"] == {
        "description": ADF,
        "labels": ["discord-support", "discord-thread-123"],
    }


def test_update_issue_raises_on_error():
    client, _ = make_client([
        FakeResponse(400, {"errors": {"labels": "Field 'labels' cannot be set."},
                           "errorMessages": []}),
    ])

    with pytest.raises(JiraError) as exc:
        client.update_issue("CUST-900", description_adf=ADF, labels=["x"])
    assert exc.value.status == 400
    assert "labels" in str(exc.value)


def test_create_request_401_raises_jira_error():
    client, _ = make_client([FakeResponse(401)])

    with pytest.raises(JiraError) as exc:
        client.create_request(service_desk_id="1", request_type_id="108",
                              summary="s", description_text="d")
    assert exc.value.status == 401


def test_429_retried_once_then_succeeds(monkeypatch):
    client, fake = make_client([
        FakeResponse(429, headers={"Retry-After": "1"}),
        FakeResponse(201, {"issueKey": "CUST-9"}),
    ])
    sleeps = []
    monkeypatch.setattr("jira_client.time.sleep", sleeps.append)

    key, _ = client.create_request(service_desk_id="1", request_type_id="108",
                                   summary="s", description_text="d")

    assert key == "CUST-9"
    assert len(fake.calls) == 2
    assert sleeps == [1.0]


def test_find_issue_by_label_returns_key_and_url():
    client, fake = make_client([
        FakeResponse(200, {"issues": [{"key": "SUP-7"}]}),
    ])

    found = client.find_issue_by_label("discord-thread-123")

    assert found == ("SUP-7", "https://x.atlassian.net/browse/SUP-7")
    call = fake.calls[0]
    assert call["method"] == "get"
    assert call["url"] == "https://x.atlassian.net/rest/api/3/search/jql"
    assert 'labels = "discord-thread-123"' in call["params"]["jql"]


def test_find_issue_by_label_returns_none_when_absent():
    client, _ = make_client([FakeResponse(200, {"issues": []})])

    assert client.find_issue_by_label("discord-thread-123") is None


def test_find_issue_by_label_raises_on_error():
    client, _ = make_client([FakeResponse(401)])

    with pytest.raises(JiraError):
        client.find_issue_by_label("discord-thread-123")


def test_429_twice_raises(monkeypatch):
    client, _ = make_client([
        FakeResponse(429, headers={"Retry-After": "1"}),
        FakeResponse(429, headers={"Retry-After": "1"}),
    ])
    monkeypatch.setattr("jira_client.time.sleep", lambda s: None)

    with pytest.raises(JiraError) as exc:
        client.create_request(service_desk_id="1", request_type_id="108",
                              summary="s", description_text="d")
    assert exc.value.status == 429
