# 2026-11-27 — The compact text and its looks are open to every group (off unless chosen)

Asked by tuananh219ln: the two-tier scene text, the three-tier title and the looks for the "Sức khỏe" groups and the others.
**This reverses** a line of [pc-text-tiers](2026-11-27-pc-text-tiers.md) ("only for the group PC Shopee, the api refuses them on any other").

- **Every group may hold** `title_layout`, `scene_text_layout`, `pc_style`, `pc_title_style` and `text_hold_sec` in its "Chữ & phụ đề"
  (`text_looks.COMPACT_FIELDS`), and a video may choose them on its Thiết lập. **Still PC Shopee's own:** the "Cộng dồn" captions
  (`text_looks.PC_ONLY`) and the new-video start (compact text on, hold 2.5 s, "Cộng dồn").
- **Off by default.** A new video of any other group starts with the boxes (`box`), as before, until its group's card or the video chooses;
  so no existing video or group changes. The AI that suggests or picks a look is still never asked for them nor accepts them.
- **"Thời gian hiện chữ"** shows on a video of any group while its scene text is two-tier (the text is hidden after 2.5 s by default when
  phrase or word captions are on, as for PC Shopee).
- **The "Sức khỏe" "Tiêu đề động" with a three-tier title** (chosen): the hook is drawn as tiers at its usual place, and the photo slots start
  under the block's real height (`title_motion.hook_bottom` already measures the title the render lays), so a two-line hook in tiers
  (about 290 px) lets the slots start higher than under the box (about 490 px, never above 640). Nothing in the motion's markup changed.
- The controls on the page are renamed "Kiểu chữ cảnh gọn" and "Kiểu chữ tiêu đề" (they no longer say PC Shopee).
