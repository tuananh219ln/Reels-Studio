# 2026-11-10 — The AI that writes a script picks the video's "Loại nội dung"

Asked by the owner (namtc) on 2026-11-10: "Loại nội dung" had to be typed on every video ("phần loại nội dung này ko
tự động mà phải nhập"); asked whether the AI should pick it while writing the script, the owner answered "Có, AI tự
chọn". It changes "a 'Loại nội dung' the member types" of "Every list of videos shows its kind" (2026-11-08): the type
is still free text a member may change, but it is no longer only typed.

- **In the script's output format** (code, docs/content.md): `content_type`, 1–4 words, one of the team's types when
  one fits, a new short one otherwise. The team's types (`videos.content_types`, the list "Loại nội dung" offers) are
  given just before the format.
- **Every script prompt has it**: the script job, "Nhân bản", "Từ video mẫu", and the prompt MCP's "Lấy prompt viết
  kịch bản của nhóm" hands to a member's assistant, whose JSON is saved the same way. No extra AI call: the type comes
  with the script.
- **A member's type wins**: the AI's is saved only on a video without one. A script written by hand has none, and videos
  made before are not filled in (that would need an AI call each).
