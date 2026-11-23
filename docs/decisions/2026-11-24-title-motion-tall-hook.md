# 2026-11-24 — A tall hook pushes a motion title's slots down

The spec fixed the slots' area at y 640–1440, which fits a two-line hook. A four-line hook ("4 TRÁI CÂY ÍT NGỌT / HỖ
TRỢ ĐƯỜNG HUYẾT ĐỪNG BỎ QUA") ends near y 750 and covered the first slots. The build now measures the text box as the
render lays it (`title_motion.hook_bottom`) and starts the slots 40 px under it (`top_for`), shrinking them to the
room left (never starting below 1000). The box stays where the spec put it, (540, 400). The layouts are measured at
build time, so changing the title text needs "Dựng lại tiêu đề".
