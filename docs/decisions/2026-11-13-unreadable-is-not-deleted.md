# 2026-11-13 — A reel the token cannot read is not a deleted reel

On the evening of 2026-11-13 two reels went live on time, and at 21:10 the check marked both "Đã xóa" and put the
videos back to "Chờ đăng". The token still read the Page (`GET /{page-id}` answered) but no longer read reels, and
Facebook answers a reel the token may not read with the same 400 (#100, subcode 33) as a reel it deleted. The
decision of 2026-11-06 took that answer for "deleted" whenever the Page still read, which was not enough.

Now a 400 (#100) on a reel means "deleted" only while the same token still reads **another reel of the same Page
that the app saw live** (`Page.witnesses`, the Page's newest three posted reels, `fanpages.load_page`;
`facebook._gone`). A 404 still means deleted. With no other reel to compare, or none that reads, the answer stays
unknown: the check and "Xóa" fail with a plain message, log a warning and leave the post as it was. "Could not read"
is never "deleted". `FacebookError` now keeps `subcode`.

A post marked deleted can be checked again (`POST /api/posts/{id}/check`, "Kiểm tra" on the video and Bài đăng
pages): a reel Facebook still has takes it back to published or scheduled, and "Bình luận ngay" shows again. One
Facebook confirms gone stays deleted. Nothing is posted or commented again by itself.

The cost: a Page with a single posted reel cannot learn that this reel was deleted in Meta Business Suite; the check
fails ("Không đọc được trạng thái reel") until the Page has another reel posted from the app.

On 2026-11-13 the saved reel ids of the two posts also differed from the reels live on Facebook (posts 68 and 71), so a
check read the wrong reel. "Sửa link reel" on a post (video page, Bài đăng) lets a member paste the reel's link; the app
saves its id and queues a check, so the fix needs no database access. Why the saved ids differed is not known.
