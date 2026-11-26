""" "Có gì mới trong app" for the assistants: the web's changelog.json, read through CHANGELOG_URL (the fake services)."""

from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)

from reels_api import changelog

ENTRIES = [
    {
        "number": 12,
        "kind": "feature",
        "title": "Đăng nhanh hơn",
        "summary": "Một bước thay cho ba.",
        "merged_at": "2026-11-26T10:00:00Z",
        "url": "https://github.com/o/r/pull/12",
        "guides": ["videos"],
        "pages": ["/posts"],
        "deployed_at": "2026-11-26T10:10:00Z",
        "author": "Nam dev",
        "author_login": "namtc07",
    },
    {
        "number": 11,
        "kind": "fix",
        "title": "Sửa lỗi cũ",
        "summary": "",
        "merged_at": "2026-11-20T10:00:00Z",
        "url": "https://github.com/o/r/pull/11",
        "guides": [],
        "pages": [],
    },
]


def test_the_assistant_reads_the_newest_changes(mcp_client, db, fakes):  # noqa: F811
    fakes.changelog = {"version": "abc", "generated_at": "2026-11-26T10:10:00Z", "entries": ENTRIES}
    _, _, tokens, _ = grant(mcp_client, db)

    answer = call(mcp_client, tokens["access_token"], "get_whats_new")

    assert not answer.get("isError"), answer
    changes = payload(answer)["changes"]
    assert [change["title"] for change in changes] == ["Đăng nhanh hơn", "Sửa lỗi cũ"]
    assert changes[0] == {
        "title": "Đăng nhanh hơn",
        "summary": "Một bước thay cho ba.",
        "kind": "Tính năng mới",
        "merged_at": "2026-11-26T10:00:00Z",
        "deployed_at": "2026-11-26T10:10:00Z",
        "by": "Nam dev",
        "screens": ["/posts"],
        "guides": ["videos"],
    }
    assert changes[1]["kind"] == "Sửa lỗi"
    assert changes[1]["by"] is None


def test_since_and_limit_narrow_the_list(mcp_client, db, fakes):  # noqa: F811
    fakes.changelog = {"version": "abc", "generated_at": "2026-11-26T10:10:00Z", "entries": ENTRIES}
    _, _, tokens, _ = grant(mcp_client, db)

    since = payload(call(mcp_client, tokens["access_token"], "get_whats_new", since="2026-11-25T00:00:00+07:00"))
    assert [change["title"] for change in since["changes"]] == ["Đăng nhanh hơn"]
    limited = payload(call(mcp_client, tokens["access_token"], "get_whats_new", limit=1))
    assert len(limited["changes"]) == 1


def test_before_the_first_deploy_the_assistant_is_told_so(mcp_client, db, fakes):  # noqa: F811
    _, _, tokens, _ = grant(mcp_client, db)

    answer = call(mcp_client, tokens["access_token"], "get_whats_new")

    assert answer.get("isError")
    assert "Chưa có danh sách" in answer["content"][0]["text"]


def test_the_web_file_is_next_to_the_public_mcp_url(monkeypatch):
    monkeypatch.delenv("CHANGELOG_URL", raising=False)
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://reels.example.vn/api/mcp")
    assert changelog.url() == "https://reels.example.vn/changelog.json"
    monkeypatch.setenv("MCP_PUBLIC_URL", "")
    assert changelog.url() == ""
