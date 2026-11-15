# 2026-11-15 — MCP tools for the whole flow: read Pages, results, jobs and comments; change the queue, plan, logo and jobs

Asked by the owner (namtc), 2026-11-15, after the list of what MCP had and lacked: "làm từ 1 đến 9". His answers on
the analysis: comments are read only; articles get full rights (a later PR, after #252/#253); paid actions are
allowed.

- **Read** (PR #256): a member's Pages and queues, published posts' numbers, the job log, visitors' comments.
- **Write, through the web's handlers** (this PR): out of the queue and its order, a plan's ideas, a video's channel
  and logo, retrying or cancelling a job, the TikTok version.
- **Paid actions over MCP are allowed** (owner, 2026-11-15): `retry_job` (a script or clone job on the team's AI, a
  render's narration on ElevenLabs) and `make_tiktok_version` (a clone job on the team's AI). Their descriptions ask
  the assistant to say the cost and call them only when the member asks, never retrying by itself, as for
  `render_video`.
- **Only the member's own jobs** are retried or cancelled over MCP, though the web lets any member: an assistant
  should not stop or rerun a teammate's work (the same narrowing as MCP deletions, 2026-11-09).
- **Comments stay read only**: answering and hiding were removed on 2026-11-10 and are not brought back.
- **Still not over MCP**: "Tạo kế hoạch bằng AI", a Page's posting times and group, accounts and tokens.
