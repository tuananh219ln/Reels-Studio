# 2026-11-25: an article's "Ảnh ghép chữ + ảnh" is one 4:5 photo drawn by the api

## Context

An article posted with a text card and a dish photo is two portrait photos, and Facebook lays two portrait photos
side by side, so the text shrinks. The spec "Ảnh ghép Thẻ chữ trên – Ảnh dưới" (25/11/2026) asks for one photo, text
band over the dish photo, whatever the order Facebook would lay out.

## Decision

- **Built as the spec says** (sizes 1080×1350, band 450 px, the auto-fit constants, `cover`/`blur`/`auto`, the
  line split, the warnings), only the preset set `cam` and `xanh_la` and only the default canvas: no other ratio.
- **Drawn with Pillow in the api** (`article_composite.py`), not in the browser: the MCP tool and the web preview
  need the same bytes. The preview and the saved photo are the same code, and the render is deterministic.
- **Font: Be Vietnam Pro Black**, the only weight the app ships (the spec says 800; the title and the pill share it).
  **Emoji are dropped** from the lines before measuring (no emoji font is shipped), as the spec's fallback says.
- **A new source `composite`** ("Ảnh ghép") with `article_images.opts` (JSON) to open it again. The dish photo is
  **copied under `opts.source_key`**, because `replace` removes the article's own photo it was made from; the copy is
  deleted with the composite. Editing draws it again from that copy.
- **`replace` (default true) removes** the article's text cards, earlier composites and the source photo, and puts the
  composite first, as the spec says. `EXTRA_IMAGES` warns when other photos stay.
- **The logo is still laid on when posting** (2026-11-15), at its place: its default corner is in the photo area.
- **The web takes the dish photo from the article's own photos** (the existing upload, library, link and stock tools
  add it first); the MCP tool also takes `media_id` and `url`. The spec's drag-to-crop is two sliders for now.
- **Default tag** `NGÀY {n} · {group}` only when the article comes from a plan day; the plan has no series name, so the
  topic group's name is used.

## Not done

- A person has not yet watched sample composites against [ux-guidelines](../ux-guidelines.md); the PR says so.
