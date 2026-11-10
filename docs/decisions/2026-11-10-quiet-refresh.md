# 2026-11-10 — Lists refresh often only while something is being made, and a failed refresh is quiet

Asked by the owner (namtc) on 2026-11-10 ("Sửa A và B") after a third screen review, this one of logic rather
than looks.

- **Refresh:** the Video list re-read every video every 5 seconds whatever was on it, and Bài viết its list every
  10 seconds; a video's page every 2.5 seconds even when only looked at. Now the Video list keeps 5 seconds only
  while a video on it is in a job (anything but Nháp, Xong or Lỗi), else 60 seconds; Bài viết keeps 10 seconds
  while an article is being written or posted, else 60; a video's page keeps 2.5 seconds while a job runs, while it
  is in "Chỉnh sửa" or while a teammate has it open, else 10 seconds. A teammate's new video can therefore take up
  to a minute to show on an open list; opening the page or the tab again reads it at once.
- **Errors:** a background refresh that fails no longer shows an error (it did on Bài viết, a Page's dashboard
  and its content list, every refresh). The load on opening still does. A video that cannot be read at all
  (the api down or a 500) shows "Không tải được video" with "Thử lại" instead of spinning for good.
- **Smaller fixes from the same review:** "Viết bằng: X, model" (the last "·" in the web's own words); "Cả đội"
  in the address is no filter in "Bộ lọc (N)"; Quản lý Page's empty card says "Kết nối Page đầu tiên" (no second
  "Thêm Fanpage") and, on an empty "Trang của tôi", "Xem tất cả Page"; a wrong "Bán tự động" time is refused and
  the saved one comes back; an empty 30-day plan names "Lập kế hoạch bằng AI"; the plan drawer counts the open
  day's ideas; Kho kiến thức's group list only stays in view beside the group, not over it on a phone.
