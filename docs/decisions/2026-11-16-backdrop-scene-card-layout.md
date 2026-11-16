# 2026-11-16 — A "Video xuyên suốt" scene card laid out as a slide video's

Asked by tuananh219ln from a screenshot of the page: on a "Video xuyên suốt" the content scenes still had the 150 px
left column (preview, a cut-off "Chỉnh vị trí chữ & ảnh chèn", the picture tools under it), while a slide video's
scenes had moved to the 182 × 324 frame with the tools' column beside it.

- [The video editor spec](2026-11-14-video-editor-spec.md) changed the frame to 182 × 324 with the tools beside it but
  left the backdrop card on the older grid, which broke "every card's frame is the same size" from
  [the scene cards change](2026-11-14-scene-cards-one-open.md). This closes that gap; it reverses nothing the owner
  chose.
- The backdrop card now uses the same layout (`.scene-body` and `.scene-media`): the 182 px preview with "Chỉnh vị trí
  chữ & ảnh chèn" under it (as wide as the preview, its label on two lines), the scene's picture tools as the same
  222 px column beside it, then the fields with the "Ảnh chèn" block under them. It folds at the same card widths as a
  slide video's scene (700 px, 440 px), measured on the card, not on the window.
- What the backdrop card shows is unchanged: the preview still plays the backdrop with the inset and text over it, and
  the tools still show only while the inset shows the scene's photo (or on an older "Ảnh món"). The studio's
  inspector keeps its one column.
