# 2026-11-09 — The plan banner and the ideas "Tạo video" suggests are of the member's own groups only

Approved by the owner (namtc) on 2026-11-09, in the review of who may edit, delete and act on what: a member who owns
no Page of a group saw "Kế hoạch …: đã làm đủ 1 video hôm nay" for a teammate's group above their videos, and the
"Tạo video" dialog offered that group's ideas, though the money of a post goes to its Page's owner (2026-10-31).

- **Only my groups**: `GET /api/plans/today` answers the groups of `routes_videos.my_topic_ids`, the groups of the
  Pages the member owns and uses ("A member's own Pages and topic groups come first where one is picked",
  2026-11-08). A member with no Page in use sees no plan banner.
- **"Tạo video" still takes any group**: picking a teammate's group and typing a topic works as before, and an idea
  opened from Kho kiến thức ("Tạo video" on the idea) is still made; only the list of plan ideas beside the form is
  left out for a group that is not mine. Kho kiến thức's plan tab and MCP's "Đọc ý tưởng kế hoạch 30 ngày" stay open
  to everyone: using a group is shared.
- This narrows, for the banner and the dialog's suggestions only, "Nothing is hidden from teammates" of "Every list
  of the team's work starts on the member's own" (2026-11-08); the lists themselves are unchanged.
