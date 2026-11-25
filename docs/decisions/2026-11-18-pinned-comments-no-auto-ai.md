# 2026-11-18 — Opening an article never calls the AI for its pinned comments; Claude through MCP can write them

Asked by tuananh219ln after seeing "AI đang viết bình luận…" on opening an article: the comments are meant to come from
the plan file (`pinned_comments`) already, or from a member's own Claude through MCP, not from the team's paid API.
This reverses the spec's "khi mở màn hình, nếu kịch bản chưa có bình luận thì tự gọi AI" (2026-11-18-pinned-comments):

- The article page shows a hint when the script has no comments; the AI runs only on "Tạo lại bằng AI", ↻ or the bulk
  "Tạo bình luận ghim", all by a member's click.
- New MCP tools: `list_article_plan_scripts` (a Page's scripts, by default those short of 5 comments, with each
  one's label set) and `save_script_comments` (the Page owner's Claude saves them as `ai`, not edited; a script edited by
  hand is refused). They call no LLM of the team.
