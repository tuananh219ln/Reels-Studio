# 2026-11-12 — "Duyệt" on the plan tab

Asked by namtc, 2026-11-12 late at night, after hunting for the approve button for the next day's
videos: the plan tab showed the ideas but no way to approve them. Approval lived only in the video
page's "Đăng bài" drawer (open the video, open "Đăng", press "Đăng" with the suggested time).

- **What:** a "Duyệt" button on an idea card whose video is ready ("Chờ đăng") and has a suggested
  post time. The confirm shows the time ("Duyệt đăng lúc ...?"); on confirm it sends the same
  `POST /videos/{id}/publish` the drawer sends — the member's own Page of the video's group,
  `scheduled_at` the plan's suggested time, `auto_comment` on — then reloads the plan, so the idea
  reads "Đã lên lịch". No new endpoint.
- **What it is not:** not semi-automatic posting, which was removed the same day. Approval stays a
  manual gate per idea; nothing is scheduled without a member's tap.
- **Blind approval:** approving from the plan tab skips watching the video. The confirm shows the
  time, and image QC still happens on the video page (and on the frame grids the night job sends).
  The night this was asked, the member had just caught two wrong images by looking at the grids.
