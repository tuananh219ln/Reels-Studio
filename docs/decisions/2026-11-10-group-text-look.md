# 2026-11-10 — A topic group has its own "Chữ & phụ đề", the AI suggests looks and may pick each video's; one "Cài đặt nhóm" tab

The owner (namtc), 2026-11-10: the text and captions belong with the group's other settings, by topic, with an AI
that suggests creative looks. Asked whether Cài đặt › Thiết lập mặc định should lose its "Chữ & phụ đề", the owner
chose to keep it, the group's over it; and for the AI, both a suggestion on the group and a pick for each video.

- **The group's own look** (`knowledge_topics.text_look`, migration 0074): the text fields of a video's settings
  (box style and colours, the title's, sizes, letter case, captions; not the text's place). None by default, so every
  group's videos keep taking their maker's until a member gives it one. The order of "Video defaults are only each
  member's own" (2026-11-09) and of the group's voice becomes, for these fields: the video's own › the AI's pick for
  it › the group's › the maker's own › the app's built-in. Thiết lập mặc định keeps its card, as the fallback.
- **"AI gợi ý"** is a job (`text_look`, one at a time per group, the team's LLM, one call asked again once), like a
  plan's "Tạo bằng AI": it writes three looks to the group (`text_suggestions`); a member puts one in the editor and
  saves it. Nothing changes on the group by itself.
- **"AI chọn kiểu chữ cho từng video"** is a switch of the group (`text_ai`), not an option of "Tạo video", so every
  way of making a video with a script written from the group's prompt (the team's AI, the semi-automatic round, the
  assistant through MCP) follows it, as for the group's "Kiểu video" the same day. The script call writes the look,
  so it costs nothing more. A named box style the AI gives is turned into a box of its colours, since the studio
  picks boxes by colour ("Kiểu hộp chữ").
- **"Cài đặt nhóm"**: the tabs "Từ cấm, ảnh & giọng" and "Mẫu dựng" become one, in two headed parts: "Viết kịch bản
  & tìm ảnh" (banned words, photo hint, stock order) and "Video mới của nhóm" (Kiểu video, voice, Mẫu dựng, Chữ & phụ
  đề), so what a new video of the group starts with is in one place.
- The look and the switch follow the group's other settings: its history and "Cho cả đội sửa".
