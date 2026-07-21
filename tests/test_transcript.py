from datetime import datetime, timezone

import transcript
from transcript import FormattedMsg, build_description_adf, build_transcript, format_message

TS = datetime(2026, 7, 20, 14, 3, tzinfo=timezone.utc)


def msg(i, content="hello", attachments=()):
    return FormattedMsg(text=format_message(f"user{i}", TS, content, list(attachments)))


def test_format_message_basic():
    line = format_message("jane_doe", TS, "my board won't boot", [])
    assert line == "[2026-07-20 14:03 UTC] jane_doe: my board won't boot"


def test_format_message_lists_attachments():
    line = format_message("jane_doe", TS, "see logs", ["https://cdn.discordapp.com/a.txt"])
    assert "[2026-07-20 14:03 UTC] jane_doe: see logs" in line
    assert "\n  [attachment] https://cdn.discordapp.com/a.txt" in line


def test_format_message_empty_content_with_attachment():
    line = format_message("jane_doe", TS, "", ["https://cdn.discordapp.com/img.png"])
    assert "[attachment] https://cdn.discordapp.com/img.png" in line


def test_build_transcript_joins_messages():
    result = build_transcript([msg(1, "first"), msg(2, "second")])
    assert "user1: first" in result
    assert "user2: second" in result
    assert result.index("first") < result.index("second")


def test_build_transcript_under_cap_keeps_everything():
    messages = [msg(i) for i in range(40)]
    result = build_transcript(messages)
    assert "omitted" not in result
    assert all(f"user{i}:" in result for i in range(40))


def test_build_transcript_over_cap_keeps_head_and_tail():
    messages = [msg(i, "x" * 1000) for i in range(100)]
    result = build_transcript(messages)
    assert len(result) <= transcript.MAX_TRANSCRIPT_CHARS
    assert "user0:" in result           # head kept
    assert "user99:" in result          # tail kept
    assert "messages omitted" in result


def test_build_transcript_truncates_giant_single_message():
    messages = [msg(0, "y" * 50_000)]
    result = build_transcript(messages)
    assert len(result) <= transcript.MAX_TRANSCRIPT_CHARS
    assert "[truncated]" in result


def test_adf_document_shape():
    doc = build_description_adf(
        thread_name="Board won't boot",
        thread_url="https://discord.com/channels/1/2",
        author_name="jane_doe",
        created_at=TS,
        message_count=3,
        transcript_text="[2026-07-20 14:03 UTC] jane_doe: help",
    )
    assert doc["type"] == "doc"
    assert doc["version"] == 1
    assert isinstance(doc["content"], list)

    link_para = doc["content"][0]
    link_nodes = [n for n in link_para["content"] if n.get("marks")]
    assert link_nodes[0]["marks"][0]["attrs"]["href"] == "https://discord.com/channels/1/2"

    code_blocks = [n for n in doc["content"] if n["type"] == "codeBlock"]
    assert len(code_blocks) == 1
    assert code_blocks[0]["content"][0]["text"] == "[2026-07-20 14:03 UTC] jane_doe: help"


def test_adf_metadata_line_mentions_author_and_count():
    doc = build_description_adf(
        thread_name="t", thread_url="https://d/c/1/2", author_name="jane_doe",
        created_at=TS, message_count=7, transcript_text="x",
    )
    text = " ".join(
        node["text"]
        for block in doc["content"] if block["type"] == "paragraph"
        for node in block["content"] if node["type"] == "text"
    )
    assert "jane_doe" in text
    assert "7" in text
