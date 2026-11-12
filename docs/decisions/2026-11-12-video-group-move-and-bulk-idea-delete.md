# 2026-11-12 — A video moves to another topic group; ideas of the 30-day plan are deleted together

The owner (namtc), 2026-11-12: delete from a group's video list, move a video to another group from its page, and
pick and delete many ideas of the 30-day plan at once.

- **Moving a video** (`PUT /api/videos/{id}/group`, "Chuyển sang nhóm khác" under "⋯" on the video page): only its
  maker, as only the maker deletes it, and not while a job holds it. Only the group changes: the look, voice, mode
  and template a group gives are taken when a video is made, so the script, photos, MP4 and posts stay as they are.
  An idea of the old group's plan made from it is freed (back to "Ý tưởng"), so that plan does not count a video
  that is no longer the group's. A clone or TikTok version keeps its own group.
- **Deleting from the list**: the video page's "Xóa video", with its confirmation, on each row and card of a group's
  "Video" tab, for the video's maker only.
- **Deleting ideas together** (`POST /api/plans/{group}/items/delete`, "Xóa nhiều ý tưởng"): the rule of deleting one
  holds for each (the member's own ideas, in a group they may edit; a video made from one stays), and the choice is
  all or none, so a refused one never leaves half a choice deleted. The web only lets the member tick their own.
