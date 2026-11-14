# 2026-11-14 — Scene cards are reordered by dragging a handle

The spec's optional point ("Kéo-thả sắp xếp thay cho ↑ ↓"), left out of
[the scene cards change](2026-11-14-scene-cards-one-open.md) and asked for afterwards by tuananh219ln.

- **A handle, not the whole row:** only the ⋮⋮ at the start of a content scene's row starts a drag, so a click on
  the row still opens the card and text in its fields can still be selected. The whole card takes the drop.
- **Dropped on a card, the scene takes that card's place** and the ones between shift by one, saved through the
  existing `PUT /videos/{id}/scene-order` (no api change). The title scene neither moves nor takes a drop.
- **The ↑ ↓ buttons stay** (on hover, as before): they are the keyboard's way to reorder, which native drag and drop
  has none of.
- Native HTML5 drag and drop, no library: the list is short and only reorders. It does not work on a touch screen,
  where the arrows remain.
- No drag in view mode or while a job locks the video.
