# 2026-11-25 — Each screen has "Hướng dẫn": Markdown guides shipped with the api

Asked by the owner ("mỗi tính năng nên có một mục hoặc tab tài liệu để hướng dẫn sử dụng, như Tài liệu của Kho kiến thức").

- **The files are in the code**: `api/src/reels_api/guides/*.md`, so a guide changes in the same pull request as its feature and
  cannot drift from it. They live in the api package, not in `docs/`, because the production image copies only `api/src` and
  `worker/src`; no deploy change is needed.
- **Read through the api** (`GET /api/guides?screen=`, `GET /api/guides/{slug}`, login required). A guide says its screen in a first
  line `<!-- screen: affiliate -->`; its title is its first heading.
- **Shown by `GuideButton`** in the screen's header, in a drawer with the notebook-style reader of the group's "Tài liệu"
  (`MarkdownReader`, shared).
- **Not** the "Tài liệu" tab of a group: that is a group's own documents, kept in the database and edited by the group.
  Guides are the app's, edited only through code.
- **Written in Vietnamese**, as the app is; `docs/` stays English. The first screen is Affiliate (a screen guide and the
  Custom Link one); other screens follow when they are changed.
