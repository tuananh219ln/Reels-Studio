# 2026-11-26 — Posting times have a time zone (VN or US), DST handled (#366)

Asked by tuananh219ln: the Page "Everyday Health Guide - US" targets a US audience but its times were entered in
Vietnam time, so posts drifted an hour whenever the US changed its clocks.
This changes the rule "times are Vietnam time" on one point: **posting times** (`plan_post_times`, `post_times`) are
written in the zone of their group or Page. Everything else the app shows stays Vietnam time.

- **Stored as wall time + IANA zone**, never a fixed offset. `scheduled_at` stays a UTC moment.
- **Zones:** `Asia/Ho_Chi_Minh` (default), `America/New_York`, `America/Chicago`, `America/Los_Angeles`
  ([schedule_tz.py](../../api/src/reels_api/schedule_tz.py)); a database check keeps other values out.
- **Group:** `knowledge_topics.schedule_timezone`, NOT NULL, Vietnam by default. **Page:** `fanpages.schedule_timezone`,
  null by default. A Page with its own times and no zone is in Vietnam (as before); a Page with no times of its own
  uses its group's times and zone. A Page's own zone needs its own times (the API refuses it otherwise): a Page cannot
  take the group's times in another zone.
- **Slots** between two moments are the zone's own days: a wall time that does not exist (the jump) takes the offset
  from just before it (02:30 becomes 03:30 EDT), one that happens twice takes its first time, and two wall times on one
  moment make one slot (a warning is logged).
- **Migration 0132** changes no behaviour and no `scheduled_at` (every zone is Vietnam).
- **Done in this slice:** columns, slot generation, the Page queue's slots (`page_queue.timezone_of`), the plan's
  suggested time, `PATCH /api/queue/pages/{id}` and `PATCH /api/plans/{topic}` taking `schedule_timezone`.
- **Web:** a VN | US switch with an ET / CT / PT list ([ScheduleZonePicker](../../web/src/components/ScheduleZonePicker.tsx))
  on the group's plan settings and on a Page with its own times; a note in the 14 days before the US changes its
  clocks; the Page's 7-day calendar groups by the Page's zone with Vietnam's time (and "(+1 ngày)") beside each slot of
  a US Page. A zone change keeps the wall hours ("Giữ số giờ") and leaves posts already scheduled alone.
- **Changing a zone:** the web asks "Quy đổi" (the times are read as the same moments in the new zone, on today's date,
  since daylight saving makes the answer depend on the day: `convert_times` on the two PATCHes) or "Giữ số giờ"
  (the default of the API: same wall hours, new zone). Posts already scheduled keep their moment either way.
- **"Ngoài khung":** posts the queue schedules record their slot (`publications.slot_local`, `slot_timezone`,
  migration 0134; null for hand-made posts and every older one). The dashboard marks a scheduled post `off_slot` when
  its moment is no longer one of the Page's slots. **No "Xếp lại theo khung mới" button:** the app cannot change the
  time of a reel already scheduled on Facebook (that is done in Meta Business Suite), so rescheduling would mean
  cancelling and posting again on Facebook; left for the owner to decide.
- **Not yet (follow-ups of #366):** the 5-minute auto-schedule with `LEAD_TIME` (the queue still fills once a minute
  with `FILL_LEAD`, 30 minutes).
- **Statistics:** "Giờ đăng hiệu quả" groups each post by its wall-clock hour in the Page's zone on the post's own
  date, so the same New York hour groups together across daylight saving; the answer carries `timezone` and the Page's
  current `post_times`, and "Thêm vào giờ đăng" adds an hour to the Page's own times in that zone.
