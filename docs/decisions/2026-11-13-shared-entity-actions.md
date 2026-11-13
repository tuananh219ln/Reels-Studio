# 2026-11-13 — The same entity exposes the same applicable actions across screens

The owner (namtc) asked to implement the entire cross-screen consistency audit, for videos and
for articles, Pages, posts, plan ideas, media, music, products and jobs.

- Shared actions own their confirmations, ownership checks and errors. Lists, cards and detail
  pages reuse them. A compact menu may hide secondary actions, but does not change permission.
- A rendered plan video's approval schedules the suggested slot after confirmation; other videos
  open the publishing drawer. Current MP4, busy-job, duplicate-post and Page-owner guards stay.
- Video lists expose publishing, queue membership, clone/TikTok, move and delete as applicable,
  the same warnings and kind labels, and quiet polling. The plan's Today strip also offers approval.
- Articles expose publishing, making a Reel and deletion on their list. Page details expose the
  same token/account/stop actions as the Page card. A Page owner can take down a teammate's post,
  as already decided on 2026-11-09; this fixes the web's narrower check.
- Post metrics, insights, comments and take-down/check actions are available wherever a post is
  managed, including a Page's content library and affiliate posting follow-up.
- A group's media tab has the library's filters, selection and item actions. Music pickers show
  source/license warnings and let a member edit a track without leaving the picker.
- Product contexts expose editing, approval and failed lookup recovery. Pickers keep their
  selection action, and destructive actions still ask and respect the maker.
- The job log gains retry and cancellation through the existing job endpoints. Cancellation is
  limited to work the backend can cancel; retry explicitly confirms that provider calls may cost.

No render changes, migration, new automatic publication or change to backend ownership rules.
