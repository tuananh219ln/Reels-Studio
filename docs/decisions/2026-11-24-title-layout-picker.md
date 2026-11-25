# 2026-11-24 — The member can pick a motion title's layout

"Dựng lại tiêu đề" always sent `layout: auto`, so a rebuild chose the layout again from the title text and a title the
member liked (a 7-dish "dải") could turn into another one (a "vòng") when its wording changed, for example when a red
`*` mark or a line break kept "kết hợp với N" from matching. The title scene now has a select beside the button
(Tự động, Lưới, Vòng, Dải, Món nên tránh). The pick is sent as `layout`, stored as `motion.title.requested` and shown
again on the next rebuild, so it sticks; "Tự động" keeps the rule of the first decision. A layout that cannot hold the
number of dishes is still refused with the same message (422). No migration: `requested` lives in the scene's motion
JSON, and titles built before it read as "auto".
