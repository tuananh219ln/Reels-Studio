# UX Guidelines

## Interface Language

**UI language:** Vietnamese only. There is no i18n for the UI.

**Content language:** a separate per-video setting. It is `vi` in the MVP, and `en` comes later.
Do not confuse it with the UI language: the script, TTS voice, and knowledge rules follow the
content language.

**Tone:** short, plain Vietnamese for an internal team. Use action-verb buttons such as "Viết kịch
bản", "Render", "Tải MP4", "Thử lại", "Nhân bản".

**Errors:** every refusal and failed job shows a plain Vietnamese reason where it happened (at the
field, the scene, or the job banner); technical detail sits in a collapsed "Chi tiết lỗi".

## ChatGPT and Claude connection

Cài đặt › Kết nối ChatGPT / Claude (`/chatgpt`) shows the copyable server URL, how to add it in
ChatGPT, Claude and Claude Code (with the copyable `claude mcp add` command), and the current
member's connections, each named by its app, with scope, expiration in Vietnam time, and “Thu hồi kết nối”. An OAuth request
opens the same page with a consent card titled “Cho phép <app> kết nối?”, naming the member and the
callback's host (with a warning for Claude Code's loopback callback), explaining read/write access,
possible script/narration costs and expiry. “Cho phép kết nối” and “Từ chối” submit to the API
and return to the app. No credentials are displayed. Missing configuration or expired consent
shows the API's Vietnamese message; the page uses the existing Ant Design theme and PageHeader.

## App Look

One theme for every screen, in [web/src/app/theme.ts](../web/src/app/theme.ts): Ant Design in the
orange of the app's icon ([web/src/app/icon.svg](../web/src/app/icon.svg)), used as the icon uses
it, and kept for two jobs only so it still points at something: the main action and where you
are. Primary buttons are filled with that orange (`#F5551F`) with white on it; the selected menu
item is a light grey fill with the deeper orange of the same hue (`#C2410C`) as its text, the
colour used wherever the brand is text or a thin mark on white (links, tabs, switches, checkboxes,
the outline round a video being edited), since the icon's orange is too light for small text on
white. Anything informational (a running job, a note, an info banner) is a quiet slate blue
(`#3B6A9A`), never antd's default blue and never the brand. Components take colours from `COLORS`
there (or antd's tokens), never a hex value of their own.

The interface reads as a tool, not a template. A status is a small dot and a word
([StatusText](../web/src/components/StatusText.tsx)): grey for nothing yet, blue while a job
runs, dark grey when done, green once out or working, amber while waiting or needing a look, red
when failed. Tags are kept for what really is a tag (a track's topics, "Mặc định", a platform).
Details are joined with commas or set on lines of their own, never strung together with "·";
there are no all-caps labels and no decorative shadows (cards are told apart by their border);
alerts are for errors and warnings that block something, plain grey text for the rest. An empty
thumbnail is a grey tile with an icon.

Every list's toolbar reads the same way: its search box first, then its filters, then its sort. A filter
is a [FilterSelect](../web/src/components/FilterSelect.tsx): typing searches its options (accents do not
matter), × clears it, and while empty it shows what "all" means ("Mọi Fanpage", "Cả đội"). The logo in the menu and on the sign-in page is that icon beside "Reels Studio". Every page behind
the login starts with the same header ([PageHeader](../web/src/components/PageHeader.tsx)): the
title with the page's main action on its right ("Tạo video", "Tải nhạc lên", "Thêm Fanpage"…), a
line saying what the page is for when it needs one, then its search and filters on one row;
lists and tables sit in white cards. The interface
font is Be Vietnam Pro (served by the app through `next/font`), radius 8 (12 on cards), controls
36 px high.

Forms open in a drawer from the right ([FormDrawer](../web/src/components/FormDrawer.tsx)), with
"Huỷ" and the main button at its bottom, so the page stays in view beside it, a long form scrolls
inside, and on a phone it takes the whole width: adding or editing a product, an affiliate
account, a Fanpage or its token, a member or a temporary password, a track, a text box style, a
plan idea, "Tạo video", "Nhân bản" / "Tạo bản TikTok", "Đăng", "Đổi mật khẩu" and "Sửa tên".
Dialogs that need the whole screen or are not forms stay centred dialogs: the photo and clip
editors, "Chọn từ kho ảnh/video", the text position, "Chọn nhạc từ thư viện", a plan's preview,
"Dán ảnh", the numbers of a Page or a post, and every yes/no confirmation.

## Screens

Built:

- **Login** and **user management**.
- **Tạo video** (on the video list): a grey strip on top holds what applies to the whole video, one row each, bold
  labels in a column (one above the other under 576 px): "Kiểu video" (not for "Từ video mẫu"), "Cách viết" ("AI
  viết kịch bản", "Từ video mẫu" or "Tự viết") and the topic group across the row; below it the topic. The footer has a
  line naming the provider and model that will write the script ("Viết bằng: … (đổi trong Cài
  đặt)"), in red with a link when that provider is not set up, on the left and "Huỷ" and the main
  button on the right. When the group's 30-day plan has ideas not made yet, the dialog widens: they
  are a list on the left (day or "Backlog" and pain group under each), in groups with their count: "Hôm nay, ngày N",
  "Ngày tới" (the next 3 days with ideas, "Xem thêm" for the rest), "Ngày đã qua chưa làm" and
  "Backlog", so videos can be made ahead and their posts scheduled, and the topic and its
  details sit in a bordered panel on the right (stacked on a phone). Picking an idea marks it
  with an orange border and "Đã chọn", fills the topic and shows its day, pain group, pain and hook; picking it
  again or "Bỏ chọn" drops it. A typed topic that is nowhere in the plan gets a yellow note that does not block.
  "Tạo video" on an idea in Kho kiến thức (`/videos?plan_item=<id>`) and "Làm tiếp" open the dialog
  with that idea picked. "Cách viết" chooses "AI viết kịch bản" (the default) or "Tự viết".
  "Tự viết" makes no AI call: every group can be picked (no "(chưa có prompt)"), the topic is also
  the title scene's text, and "Kịch bản (không bắt buộc)" takes a pasted script. Its placeholder
  shows the format: a paragraph per scene, "Đọc:" lines for the voice text. A yellow note says that
  no title options, caption, hashtags, photo keywords or safety self-review will come and that the
  member checks the content against the channel's safety rules. The provider line is hidden and
  the button reads "Tạo video". The video page opens with the scenes ready to edit. The title card
  says "Kịch bản tự viết, không qua AI", and "Nội dung đăng" shows a yellow warning in place of the
  AI's self-review.
  "Từ video mẫu" learns the script from a sample video: every group can be picked (the group's
  sample prompts have defaults) and the plan's ideas are not listed. "Cách làm" picks one of five
  ways, with what it does written under the choice: "Nhanh" (the default), "Hai bước tự động",
  "Duyệt phân tích trước", "Dùng mẫu đã học" and "Edit từ footage" (the member's own footage, cut
  by what is said and keeping its sound; no AI writes; it needs an ElevenLabs key with Speech to
  Text, and its source field reads "Footage", its topic field "Tiêu đề video", the title scene's
  text). The ways other than "Dùng mẫu đã học" take the sample under "Video mẫu":
  "Dán link" (TikTok, YouTube Shorts or a video file's link) or "Tải video lên" (a drop zone for one
  MP4, MOV or WebM, 100 MB and 3 minutes at most); "Dùng mẫu đã học" instead lists the samples
  learned before (link or file name, length, how many videos) and shows the chosen one's analysis.
  The topic field reads "Chủ đề hoặc yêu cầu cho video mới". The main button reads "Viết kịch bản",
  or "Phân tích video mẫu" for "Duyệt phân tích trước". "Tạo thêm video từ mẫu này" on a video page
  opens the dialog (`/videos?reference=<id>`) on "Dùng mẫu đã học" with that sample chosen.
- **Video list** (`/videos`): "Tạo video"; then, on one row, the search by title or topic and the filters:
  status (Cần làm: a draft older than 2 days, a failed job, an MP4 behind the edits, or a finished video not out
  on Facebook or TikTok; Nháp, Đang xử lý, Xong, Lỗi, MP4 cần render lại), platform, Fanpage (any Page the video
  is out on or set for), topic group ("Sức khỏe (12)", its number of videos; remembered in the browser) and
  creator ("Của tôi" first, then the team), each showing "Mọi trạng thái", "Mọi nền tảng", "Mọi Fanpage", "Mọi
  nhóm chủ đề" or "Cả đội" while empty; sort "Mới nhất" or "Nhiều view nhất". With a group chosen, a grey line
  under the filters counts its videos made this week (from Monday, Vietnam time): new, out, still drafts. Every card, row
  and video page names its platform ("Facebook" or "TikTok") beside its status. A TikTok version sits on its source's card (or row) as a small "TikTok ·
  Nháp" / "TikTok · Đã đăng" link that opens it, not on a card of its own; it gets its own card when a platform
  is chosen or its source is filtered out. A Facebook video at 3× its Page's median or more at 48 hours with no
  TikTok version shows "+ Tạo bản TikTok" there instead, opening its "Tạo bản TikTok" drawer. Two views, remembered in the browser; a click opens the video:
  - a grid of cards on their side (1 to 4 a row by width), equal in height. The 92 px thumbnail is
    left as it is (or a grey tile with an icon) but for one dark badge in its corner, as on a profile
    grid: the views ("12,4K", the latest readings of every live post added up) or the scheduled day.
    Beside it, top to bottom: the title (2 lines, in full on hover); the post's Page ("và N trang khác"
    for more, a long name cut and in full on hover) and "Đăng 03/11 07:00" or "Hẹn đăng 05/11 20:00"
    (the year only when it is not this one), or "Chưa đăng"; at 48 hours "N× trung vị" (orange and
    bold from 10×) and "N% share" (green once it reaches the goal); a warning on its own line (a job's
    stage while posted, "Render lại lỗi", "MP4 chưa cập nhật theo bản sửa"); then the status as a dot
    and a word ("Đã đăng", "Đã lên lịch", or Nháp / Chờ / Đang viết / Đang render / Xong / Lỗi, with
    "TikTok" after it) and on the right the creator and the day it was made; under them, small, the
    topic group and its plan day;
  - a list, one row per video: small thumbnail and title, the status (with "Đã đăng" or "Đã lên lịch"
    under it), "Đăng" (Page and time, or "Chưa đăng"), "View" (sortable), "48h" (the multiple or
    "chưa đủ dữ liệu", the share/view under it) and "Tạo" (group, plan day, creator, day). Above the videos, one
  banner per topic group whose plan has a today: "Kế hoạch <nhóm>, ngày N: hôm nay còn X/Y video"
  with "Làm tiếp" (the next idea not made), or green once all of today's ideas have a video.
- **Video editor** (`/videos/[id]`), updating itself while a job runs and while teammates edit.
  A video made "Từ video mẫu" has a "Video mẫu" card above the scenes: the sample's link (opens in a
  new tab) or file name, its length and the way chosen; the AI's analysis, the stills (a strip of
  small 9:16 pictures with their second, what the AI saw in each on hover) and the sample's words
  folded under "Lời thoại video mẫu". Before the script these show open; once it is written they fold
  under "Xem phân tích, khung hình và lời thoại". In "Duyệt phân tích trước" the analysis waits in a
  text box with "Viết kịch bản" (saves the edit, then writes; the header's "Viết kịch bản" is hidden
  meanwhile) and "Lưu phân tích". The card's header has "Tạo thêm video từ mẫu này" once the sample is
  analysed and a bin that deletes the sample after a confirmation (the videos made from it keep their
  scripts and clips; the card then says the sample was deleted).
  The scenes fill the left column. The right column is a panel with three tabs, "Xuất bản" (the MP4
  as a small player beside its length, with the listening volume under it, "Tải MP4", "Đăng" and "Thêm vào hàng chờ", then the video's posts), "Thiết lập" (the video's own settings: narration and music) and "Nội dung
  đăng" (the post texts); until a member picks a tab it shows "Thiết lập" while there is no MP4
  and "Xuất bản" once there is. On a wide screen the panel stays in view while the scenes scroll.
  "Thêm vào hàng chờ" (a Facebook video) opens a drawer with a reminder to watch the MP4 first, the Page
  ("Page của tôi cho nhóm “…”" by default, or any Page in use) and "Tự bình luận"; once queued, the button
  becomes "Trong hàng chờ của “Page”" (linking to Quản lý Page), with the reason when it could not be
  scheduled and "Bỏ khỏi hàng chờ"; it comes back once the worker has scheduled the post.
  "Render" and "Tạo ảnh AI cho cảnh thiếu" sit in a bar stuck to the bottom of the screen, which
  counts the red reasons still blocking the render ("Còn N lỗi cần sửa") and scrolls to the first
  one when clicked, opening the scene that holds it. While a job runs, the bar says which one with
  a spinner and its running time ("Đang render video… 0:42 / khoảng 1:15", the estimate being the
  last render's time), or that it is queued, with "Hủy"; a render seen to finish says "Đã render
  xong MP4". With nothing running, it says how the MP4 stands ("Sẵn sàng render." before the first
  one, "Bản sửa chưa có trong MP4" in orange after an edit, else "MP4 đã theo bản mới nhất."), and
  under that a summary: content scenes, the length the scenes add up to, narration on or off, and
  the current MP4's length. Once there is an MP4 the button reads "Render lại". The editor has:
  - **View and edit mode**, for the whole page. A video already rendered or posted opens in view
    mode ("Xem"), so a stray click cannot change it: every scene field reads as plain text, and
    the title choice, scene move/delete/add, every photo and clip action, "Vị trí chữ", music
    and the "Thiết lập" tab are disabled. Still available: opening and closing scenes, playing
    previews and the MP4, "Tải MP4", "Nhân bản", "Xóa", "Render", the "Xuất bản" tab and the
    post texts under "Nội dung đăng" (they are not part of the video). "Chỉnh sửa" beside
    "Nhân bản" unlocks the page, shown by "Đang chỉnh sửa" in grey by the title and a light
    orange outline round the scenes; fields still save one by one when left, so there is no "Huỷ".
    "Xong" saves the field being typed in and locks the page again, unless a save was refused
    (then a message points to the field). A video never rendered opens in edit mode. The mode is
    chosen when the page opens and is not stored;
  - **who else is here.** Under the title, "Đang ở đây:" and the avatars of the other members
    with the video open (not yourself; one per member, however many tabs). An avatar has a blue
    ring when that member is in "Chỉnh sửa", and its tooltip says "<name>, đang chỉnh sửa" or
    "đang xem". It updates within about 10 s, and a closed tab leaves at once. Pressing "Chỉnh
    sửa" while someone else is editing shows a warning naming them ("Bình đang chỉnh sửa video
    này…"), but still unlocks the page: nothing is locked, the last field saved wins;
  - **scene cards that open and close.** A closed card's title row shows a 40×40 thumbnail of
    the preview, "Cảnh N" (or "Cảnh tiêu đề"), its seconds, its text on one line (without the
    `*` marks) and a status: red "N lỗi", amber "N cảnh báo" or green "Sẵn sàng"; an open card
    shows the name, seconds and tag. A click or Enter anywhere on the row opens or closes it;
    the move and delete buttons beside it do not. When the page opens, a draft's scenes are all
    open; in a rendered video only the scenes with a red reason are. "Mở tất cả" and "Thu gọn
    tất cả" sit above the list. A closed card keeps its fields, so closing never loses text;
  - inside an open card, two columns (stacked on a phone, the picture first): the 9:16 picture
    with its tools on the left, the fields on the right: "Chữ trên màn hình" (a "?" beside it
    explains `*từ*` and line breaks), "Lời đọc", "Số giây" and "Bắt đầu từ giây" (clip only) side
    by side, "Từ khóa tìm ảnh", "Prompt ảnh AI" (every scene, the title included; its "?" says to
    describe what is in the photo, in English, since the shared style is added), then the reasons and
    warnings. Under the text and the voice text a counter shows the words as typed (the `*` not
    counted), in yellow outside the script's lengths ([content.md](content.md): at most 10 words
    on a scene, 12 on the title; voice text 8–15 words, 8–12 on the title); it never stops a save;
  - **"Xem trước"** in the render bar, and "Xem từ cảnh này" (a play icon) on every scene card,
    play the video in the browser before any render, in a drawer from the right that leaves a strip
    of the page in sight and is laid out like a video editor: a tools column on the left ("Cảnh":
    the scene list; "Chữ & sticker": "Thêm chữ" and the stickers, each added to the scene shown from the
    playhead's second for 2 s, never to the title scene; "Âm thanh": every sound effect with "Nghe" and "Thêm"
    (added to the scene shown at the playhead), and "Bài nhạc bắt đầu từ giây" when the video has music; "Tự dựng":
    each "Mẫu dựng" (the app's "Gợi ý của app" first, then the team's) with what it does and "Áp cho cả video"
    (undone with Ctrl+Z), and "Lưu video này thành mẫu"; "Góp ý":
    the notes in the order of the video (second, who, Chưa gửi / Chờ AI sửa / Đã sửa, the AI's answer, "Xoá") and
    "Nhờ AI sửa (N góp ý)", asked first since it costs one AI call; "Khung":
    the app frame and the safe zone; "Giọng
    đọc"), its panel beside it, the
    phone in the middle on grey, "Chỉnh cảnh N" on the right and the timeline along the bottom (up to
    1280 px wide "Chỉnh cảnh N" sits under the tools' panel; under 900 px they stack: phone, timeline,
    tools, panel, "Chỉnh cảnh N"). "Chỉnh cảnh N" holds everything about the scene shown, in folding
    sections: "Nội dung" (the scene card's own "Chữ trên màn hình" and "Lời đọc" fields), "Thời lượng và
    vị trí chữ" (below), "Ảnh của cảnh" / "Video của cảnh" (the card's upload, paste, Google, TikTok, "Chọn
    từ kho ảnh/video", "Đã dùng trong nhóm", "Tìm ảnh" and "Tạo ảnh AI", with "Chỉnh khung" for a photo and
    "Xoá video" for a clip; the phone shows the picture) and, folded, "Tìm ảnh: từ khoá và prompt AI". These
    are the same fields as on the scene card and save the same way, so the card and the studio always agree.
    "Chữ & sticker (N)" lists the scene's layers; the one picked (on the phone or in the list) opens for its words,
    "Kiểu chữ", size, "Hiệu ứng vào", start and length, and "Xoá lớp". On the phone each layer shows for its own
    seconds as the render lays it on; while paused it is picked with a click (outlined) and dragged to a new place;
    Delete removes the picked layer instead of the scene, Esc lets it go. Every layer change can be undone.
    "Âm thanh (N)" sets "Nhạc ở cảnh này" (Theo video, Tắt nhạc, Nhạc nhỏ, Nhạc to; shown when the video has music)
    and lists the scene's sound effects, each with "Nghe", its second, its level and "Xoá"; also undone with Ctrl+Z.
    The keys and how to edit on the phone sit behind "Phím tắt" (?) in the timeline's header. Under the timeline
    "Góp ý tại 00:04,2: gõ rồi Enter" keeps a comment at the playhead's second (even in "Xem"); each shows as a dot
    on the ruler (yellow until answered, then green) that goes to its second. It plays each
    scene for its seconds (lengthened to fit its narration), the frame
    without text moving like the video's motion setting with the exact text box on top where the
    render puts it, clips from their start time, the video's transition (crossfade, cut or slide),
    the music from where that scene falls in the video (lowered while narration plays when ducking
    is on). Narration: the ElevenLabs MP3 when one was made for the current text (by a render or
    by "Tạo giọng ElevenLabs"), else the browser's own Vietnamese voice (free, at the video's speed). The
    "Giọng đọc" section picks the video's ElevenLabs voice with "Nghe thử" (the same choice as "Thiết lập";
    a new voice makes each scene's narration again), says how many scenes lack the MP3, and offers
    "Tạo giọng ElevenLabs cho N cảnh", which asks first (it costs credit once) and queues a job reading only
    those scenes. "Giọng tạm của trình duyệt", folded, lists the browser's Vietnamese voices, the most
    natural first (Edge's HoaiMy/NamMinh, then Google's), remembered in the browser, and suggests Edge
    when only robotic ones exist; a browser without a Vietnamese voice says so and those scenes stay
    silent. "Thời lượng và vị trí chữ" edits the scene being shown, saved at once as on its card (read-only
    until "Chỉnh sửa" and while a job runs): its seconds with "Tự khớp lời đọc" (typing them turns it off), the
    narration's length; for a clip, a two-handle "Đoạn clip" slider (the left end is "Bắt đầu từ giây", the
    span the scene's seconds at the clip's speed); and, while the preview is paused, the text box dragged
    on the phone itself, kept inside the safe zone as the render places it, for "Cảnh này" or "Mọi cảnh",
    with "Về vị trí chung". While paused and editable, the phone itself is edited: a double-click on the text box
    types its on-screen text in place (opened with it all chosen; leaving the field or Ctrl+Enter saves, Esc
    cancels); the box snaps to the frame's middle with a guide line; with a TikTok/Reels/Shorts frame on, a box
    under the app's right-hand buttons or caption is outlined in red with "Hộp chữ bị … che"; on a touch screen the
    box moves after a short hold, and a quick swipe across the phone changes scene. On the timeline a segment's
    right edge drags its seconds (1–10, by tenths; a double-click goes back to "Tự khớp lời đọc") and a content
    scene's segment drags to a new place. Under the scenes' track the timeline has a track each for what plays with
    them, named in a column at its left: "Chữ" (each scene's on-screen text across the scene), "Lớp" (each text
    or sticker layer for its seconds; a click goes to its first second), "Âm" (each sound effect while it is heard;
    a click goes to its second), "Giọng" (the
    narration from 0.2 s into its scene for the MP3's length; dashed, as "Giọng tạm", while only the browser's voice
    reads it), "Phụ đề" (only when the video's captions are on; never on the title scene) and "Nhạc" (the music's
    name across the video, only when it has music). A click on a block plays its scene (on "Nhạc", goes to that
    second). The "Cảnh" and "Chữ" tracks have a padlock: a locked "Cảnh" track keeps the seconds' edges, the
    reorder drag, the trim bar, [ ], "Tách cảnh", "Thêm cảnh" and "Xoá cảnh" out of reach; a locked "Chữ" track
    keeps the text box from moving or being typed over; a locked "Lớp" track takes no new layer and keeps the
    layers as they are. Locks are each member's own, per video, remembered in the
    browser, and "Chỉnh cảnh N" says when one is on. A scene with a clip gets a trim bar under the phone: the
    window moves the start, its ends set the start and the seconds, and the phone shows the frame being chosen. A
    toolbar beside the phone has "Hoàn tác" / "Làm lại" (also Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y) for these changes, a
    new photo or clip, the video's "Chuyển cảnh", "Tách cảnh tại đầu phát" (S; the scene ends at the playhead, at
    least 1 s from either end, and the rest becomes a new silent scene without text showing the same photo or the
    clip from where the first part stops; it can be undone), "Thêm cảnh sau cảnh này" and "Xoá cảnh" (Delete; asked
    first; neither of the last two can be undone). Keys: Space plays or pauses, ← → change scene, [ ] take or add
    0.1 s. The video plays inside a phone with the chosen app's own
    screen drawn over it, "Khung ứng
    dụng": Reels (the default), TikTok, Shorts or "Không". Each is laid out like the app (top bar,
    right-hand buttons with counts, avatar, channel and follow button, the video's caption and
    hashtags on one line, the music's name, the navigation bar; Shorts' red progress line), with
    generic icons and the video's Page as the channel, so the member sees what each app covers.
    The choice is remembered in the browser. A switch adds the template's safe zone as a yellow
    dashed box. The timeline has a ruler in whole seconds ("00:07"), one segment per scene as long
    as the scene with its picture repeated along it and "Cảnh N, Xs" on it (the current one
    outlined), and a playhead that follows the preview. A click on a segment plays that scene; a
    press or drag on the ruler or the playhead goes to that second and pauses there (← → on the
    focused playhead move 0.5 s, 1 s with Shift; Home and End go to the ends), and "Tiếp tục" plays
    on from there: the clip, the motion, the music and an ElevenLabs narration from that point, the
    browser's voice only from a scene's start (it cannot start mid-sentence). Its header holds the
    buttons (back to the start, previous scene, "Tạm dừng" / "Tiếp tục" ("Xem lại" at the end),
    next scene, the listening volume), the time ("00:01,5 / 00:08,0") and a zoom (1× fits the whole
    video, up to 8×; the track then scrolls and follows the playhead while playing). The scene list
    under "Cảnh" (name, text, seconds) also jumps. A note says it is close to the MP4 but not the MP4 (captions and the audio mix come
    only with a render). It is available in view mode too;
  - choose 1 of 5 titles (the card names the provider and model that wrote the script, "Kịch bản
    viết bởi …"); edit the title scene and every content scene (text with `*word*` in
    red, voice text, seconds, image prompt), add, delete, reorder; each field saves when left and
    shows "Đã lưu";
  - per scene a preview of the frame, or the reason there is none, in red. Pointing at a picture
    (always on a touch screen) dims it and stacks its tools in its middle, all the same width: "Xem"
    (the only tool in view mode: a centred dialog with the scene large in its 9:16 frame, the photo
    as the render crops it or the clip looping the part the scene plays, muted, at its speed, and
    the exact text box where the render puts it, with a "Chữ trên màn hình" switch to hide it), "Chỉnh khung" for a photo or "Cắt video" for a clip, "Vị trí chữ" and, for a
    clip, "Xoá video" (confirmed). Under the picture one row: a slim
    dashed area, "Tải lên", beside three icon buttons, "Dán ảnh/link", "Tìm trên Google" and "Tìm
    trên TikTok". The dashed area takes a photo
    (JPG, PNG, WebP, 15 MB) or a clip (MP4, MOV, WebM, 50 MB) dropped on it or chosen, and a photo
    dragged straight from another tab (its address is read from the drop); a photo in place of a
    clip, or a clip in place of a photo, asks first ("Đổi" / "Huỷ"). "Dán ảnh/link" reads a copied
    photo or a link from the clipboard, or opens a box to paste into ("Dán ảnh hoặc video cho …",
    "Lấy về") when the browser does not allow it; Cmd/ Ctrl+V anywhere in the picture column outside
    a text field does the same. A link may be a photo's, a video file's or a TikTok video's; a video
    longer than 60 s keeps its first 60 s. "Tìm trên Google" opens Google Ảnh in a new tab, tall
    photos only, and "Tìm trên TikTok" TikTok's video search, to copy a photo or a video's link and
    paste it back; with more than one keyword each button first lists them ("… với từ khóa:", Google
    the Vietnamese then the English ones, TikTok the Vietnamese ones) and opens on the one picked. With the team's
    Chrome extension ("Reels Studio – Google Ảnh", `extension/`), "Tìm trên Google" also makes that scene the target
    of "Gửi ảnh vào Reels Studio: <cảnh>" on any image's right-click menu, which puts the photo on it like a pasted
    link; and the render bar shows "Lấy ảnh Google cho cảnh thiếu ảnh" beside "Tạo ảnh AI cho cảnh thiếu", which
    searches Google Ảnh for every scene without a photo or clip (its first two keywords) and puts the first usable
    result on each, marked "Tự chọn, kiểm tra lại", then says how many it filled; a CAPTCHA stops it with a dialog
    saying to solve it in the Google tab and press again. Without the extension neither shows. Then
    "Chọn từ kho ảnh/video", "Đã dùng trong nhóm" (a dialog of the photos and clips the group's other
    videos use, best match for the scene's keywords first, a search box that ignores accents, and
    "Dùng" on each, which copies it into the scene, asking first when the scene has a picture), "Tìm ảnh" with its source arrow,
    then "Tạo ảnh AI" ("Tạo lại ảnh AI" when the photo is already an AI one): an image job for this
    scene only, from its saved prompt, that replaces the scene's photo or clip, asking first when
    there is one; while it runs the button reads "Đang tạo ảnh AI…" and the job bar says "Tạo ảnh AI
    (1 cảnh)". Its arrow, like the one beside "Tạo ảnh AI cho cảnh thiếu", offers "Tạo bằng
    Cloudflare" / "Tạo bằng Gemini" for this press (one without a key is greyed out); the button
    itself uses the team's default;
  - **"Sửa ảnh"** (a photo, over the picture beside "Chỉnh khung", and in the studio's scene panel): a dialog with the
    photo on the left and two tabs. "Xóa vùng": the member drags (mouse or finger) to draw up to 10 red boxes over a
    logo, a watermark or a stray object, each with its own × and "Bỏ hết khung", then picks "Xóa nhanh (miễn phí,
    chạy trên máy chủ)" (LaMa, the default) or "Cloudflare" with an optional "what to paint there"; "Xóa vùng đã
    khoanh" is enabled once a box is drawn. "Sửa theo mô tả": a text box for what to change, with a warning that
    each edit costs Gemini; the button reads "Sửa ảnh". In "Xóa vùng", "Tìm chữ/logo tự động" runs a free job that
    finds writing on the photo and adds a box around each (the dialog follows the job and says what it found; a logo
    without letters is not found, and the member checks the boxes before erasing). Either queues an image_edit job: the card shows "Đang sửa
    ảnh…" and the job bar "Sửa ảnh (1 cảnh)". An edited photo shows "Ảnh đã sửa" under it, with "Khôi phục ảnh
    gốc" (asks first), which brings back the photo from before the first edit;
  - **"Làm mờ vùng"** (a clip, over the picture and in the studio's scene panel): a dialog with the scene's frame as
    the video shows it, where the member draws up to 10 boxes over a logo or channel name burned into the clip;
    "Lưu vùng mờ" saves them at once (no job) and the next render blurs them for the whole scene; the card says
    "Làm mờ N vùng trên video" and its previews show the blur. "Bỏ làm mờ" takes them away;
  - a photo pasted from a stock site's link (Shutterstock, Getty, iStock, Adobe Stock, 123RF, Dreamstime…) is kept,
    with a warning that its preview carries a watermark and needs a licence;
  - **listening volume** ("Âm lượng nghe"): a speaker button that mutes ("Tắt tiếng" / "Bật tiếng")
    and a slider from 0 to 100 %, beside the preview's play buttons, under the MP4 in "Xuất bản",
    and in "Cắt video" once "Nghe tiếng gốc" is on. It is how loud this browser plays, never part of
    the video: it multiplies the video's own mix (music, narration, ducking keep their proportions),
    changes nothing rendered or posted, and is remembered per browser, the same level for every
    player. The MP4's own mute button moves it too. The browser's free voice takes a new level from
    its next scene. The plain audio players (narration of a scene, music, the music library) keep
    the browser's own volume control.
  - "Chỉnh khung" and "Cắt video" open in the middle of the screen, the picture on the left and its
    controls in labelled groups beside it (under it on a phone), so "Áp dụng" needs no scrolling; the
    other picture dialogs (Vị trí chữ, the paste box, Chọn từ kho) are centred too.
  - **"Chỉnh khung"** (photo): a dialog that crops the photo to 9:16 with a "Phóng to" slider
    (1–4×), "Xoay 90°", "Lật ngang" and "Đặt lại"; dragging moves the photo under the frame. "Áp dụng" cuts
    it in the browser to a JPEG of at most 1080×1920 and stores it in place of the photo, keeping
    where it came from (Pixabay, an AI model…); a crop narrower than 1080 px warns that the photo
    will look soft. Cropping again starts from the cropped photo: picking the photo again is the
    way back. **"Cắt video"** (clip): a muted 9:16 player and a two-handle slider over the clip;
    dragging a handle shows its frame, "Xem thử" plays the chosen part only at the chosen speed,
    and the scene's length is the part divided by the speed, less the crossfades (0.2 s on each
    side with a neighbour). "Tốc độ clip" goes from 0,5× to 2× in steps of 0,25 (1× by default);
    changing it keeps the scene's seconds and moves the end of the part. A part longer than the
    clip left after the start warns that the last frame will hold, and can still be applied. A part
    shorter than 1 s or longer than 10 s cannot be applied. "Áp dụng" saves the start, the speed and
    the seconds together. Under "Tiếng gốc", "Nghe khi xem thử" plays the clip's sound in the dialog, and
    "Giữ tiếng gốc khi xuất video" keeps it in the MP4 (saved with "Áp dụng"; refused for a clip without
    sound), with a note: the MP4 has the clip's sound, and captions follow the clip's words when it has
    them, or the MP4 does not use it. The studio's preview plays a kept sound too, at the listener's level;
    with narration on, a note says the scene may last longer to fit it;
  - per scene with text and a picture, "Vị trí chữ" ("Vị trí chữ (riêng)" once the scene has a place
    of its own) opens a dialog: the frame without text at a quarter size, the platforms' covered
    areas darkened and the safe zone dashed (x 60–940, y 220–1440), and the exact box image dragged
    with the mouse or the arrow keys (10 px a press); the box stops at the zone's edges, and a box
    wider than the zone stays centred across. Buttons: "Vị trí gốc" (back to the template's place),
    "Lưu cho cảnh này", "Lưu cho mọi cảnh" (the video's place for every content scene without one of
    its own), "Bỏ vị trí riêng của cảnh này" and "Đưa vị trí chung về gốc". The title scene's dialog
    moves only up and down and has "Lưu"; it is also the thumbnail. Captions sit above a moved box,
    or under it when they would reach past the top of the safe zone;
  - under the MP4 on "Xuất bản", "Kiểm tra chất lượng" lists the automatic QC, failed checks first, each a
    status dot with its label and measure; the title says "Đạt chuẩn đăng", "Đăng được, nên xem lại" or "Chưa đạt,
    nên sửa rồi render lại". It is advice: posting is never blocked by it;
  - a "Cảnh động" shows its status under the picture: "Đang dựng cảnh động" while its job runs, then
    "Cảnh động · N giây". It is changed through the assistant; another photo or clip replaces it as usual;
  - a photo picked by "Tự tìm ảnh" carries an amber "Tự chọn, kiểm tra lại" status under the picture
    with "Giữ ảnh này"; keeping it, or changing the photo any other way, removes it. It never
    blocks the render;
  - per scene (title included) a "Từ khóa tìm ảnh" field and two Pixabay buttons: "Chọn từ
    Pixabay" opens a dialog with the scene's first keyword already searched (editable, Enter
    searches again), the scene's keywords as chips under the box (the source's language first; a tap
    searches it), the filters "Hướng ảnh" (Dọc, the default | Vuông | Tất cả) and "Ẩn ảnh đã dùng
    trong video này" (on by default; any change searches again; photos too small for the frame are
    always left out), and every result as a grid of 9:16 tiles, each photo cropped as the render
    will crop it, that fits the screen (two columns on a phone); clicking one stores it for the scene, closes the dialog and puts the keyword that found
    it first in the scene's keywords. "Tìm ảnh" (with its source, e.g. "Tìm ảnh (Pexels)") takes
    the next result for the saved keywords from the source named on the button (Pexels, or the first
    source offered when Pexels is not, until another is picked from the arrow menu beside it). The
    picker opens on Pexels the same way. The picker's source tab stays as chosen while the page
    polls. Each scene shows its own spinner and the api's
    message word for word; without keywords it also points to the keyword field. The dialog (now
    "Chọn từ kho ảnh/video") has an "Ảnh | Video" switch when a source offers clips: "Video" lists
    vertical stock clips from Pexels and Pixabay (English keyword first) as 9:16 stills with their
    length, playing muted when pointed at; clicking one stores it as the scene's clip, like
    an uploaded clip, in place of its photo or clip. Sources turned off on Nguồn tư liệu are left out;
  - blocking reasons in red at the scene, warnings in yellow; a scene with neither a photo nor photo
    keywords (a script can leave them out) warns "Cảnh chưa có từ khóa tìm ảnh"; "Render" is disabled until nothing
    blocks;
  - once a render has made a scene's narration, its player, length, and the lengthened scene;
  - the "Thiết lập" tab, every change saved at once, with a row of buttons on top (Âm thanh, Nhạc
    nền, Hình ảnh, Chữ & phụ đề) that scrolls the panel to that group: "Âm thanh" (narration on/off, the
    voice picked from the ElevenLabs account's voices, and VieNeu's once its key is set, grouped "ElevenLabs" and "VieNeu"
    when both have voices, with "Nghe thử" playing ElevenLabs' free sample (VieNeu voices have none), the
    "Tốc độ đọc" slider (0,70× to 1,30×, marked Chậm/Vừa/Nhanh), voice level, "Nhỏ nhạc khi có giọng đọc"); the music card (from the library
    ("Chọn từ thư viện", filtered by topic, mood, and name) or an uploaded MP3, optionally saved to
    the library with its topics and mood, with a volume slider); "Hình ảnh" (Chuyển cảnh: Mờ dần,
    Cắt thẳng, Trượt; Chuyển động ảnh: Zoom vào, Zoom ra, Lia ngang, Đứng yên; Độ zoom: Nhẹ, Vừa,
    Mạnh); "Chữ & phụ đề" (a "Chỉnh chữ cho" switch at the top, Các cảnh or Tiêu đề: Tiêu đề shows
    "Tiêu đề giống các cảnh", ticked by default (and unticked, with the yellow box, for a video made
    with the older "Hộp vàng"); unticking starts the title's own look from the scenes' and shows the
    same cards and colour rows for the title only; ticking it again drops the title's look; the
    captions are shown under Các cảnh only, with a note that the title is the thumbnail. For each, the
    Kiểu hộp chữ chosen from small 9:16 previews, every card the same width with its preview on top
    and a one-line name under it (a long name is cut with "…" and shown whole in a tooltip): Không
    hộp, then the team's own box styles, then a "Thêm kiểu" card with a dashed "+" preview, opening "Thêm kiểu hộp chữ" (Tên kiểu, Màu nền
    hộp, Độ trong của hộp: Đặc, Hơi trong, Trong, Không nền; Màu chữ; Màu chữ đánh dấu, with a live sample and the
    readability warnings); a new style is picked at once; under the cards the picked style's name with
    "Sửa kiểu" and "Xoá kiểu" (confirmed: "Video đã dùng kiểu này vẫn giữ màu của nó."); the styles are
    shared by the whole team and a video keeps a copy of the colours, so editing or deleting a style
    never changes a video; then three colour rows, Màu chữ, Màu chữ đánh dấu and Màu nền hộp (Màu viền chữ for
    Không hộp), each with Theo kiểu, eight swatches (Trắng, Đen, Vàng, Đỏ, Cam, Xanh lá, Xanh dương,
    Hồng) and "Tuỳ chỉnh" opening a colour picker; a faint pair is allowed with a warning under the
    rows ("Chữ khó đọc trên nền hộp này. …"); Độ trong của hộp (Theo kiểu, Đặc, Hơi trong, Trong, Không nền) while
    the style has a box, Không nền turning the box colour row into Màu viền chữ; these rows change only the video (or the defaults), not the team style, whose card
    is then no longer marked; picking Không hộp puts the box colour and opacity back to Theo kiểu;
    Phụ đề theo giọng đọc: Tắt, Từng cụm, Từng từ, greyed out while narration is off); and "Lấy
    theo mặc định nhóm" with a confirmation. A new video starts with the team's defaults; a clone
    with its source's. MP4 player, "Tải MP4", and the render time are on "Xuất bản";
  - post content (caption, hashtags, affiliates, pinned comment, music suggestions) with copy
    buttons, and Claude's self-review list. On a Facebook video, "Sản phẩm gợi ý từ Shopee" lists
    Shopee's products for each product idea (photo, price, stars, sales, shop type, commission and
    money per order) with "Chọn", "Tìm sản phẩm" / "Tìm lại", and links to Shopee Affiliate's own
    search when there is nothing yet. Under them, "Dán link aff Shopee" takes the links copied from
    Shopee Affiliate's "Lấy link" (one per line) and lists them as "Link đã dán": read by the worker
    when the team has an App ID ("Đang lấy thông tin từ Shopee…"), otherwise "Chưa có thông tin sản
    phẩm" with "Sửa thông tin", the product form, until it meets the rules and offers "Chọn". The
    products picker shows only the video's platform's products;
  - "Tạo bản TikTok" (on a Facebook video) opens "Nhân bản" with a TikTok request filled in; the
    new video is tagged "TikTok" (on the list it sits on its source's card, see above) and both pages link
    to each other: "Bản TikTok: …" on the Facebook video, "Bản Facebook gốc: …" on the TikTok version (the two
    usually share a title, so the label says where the link goes). The TikTok version is optional: any video's own MP4
    goes to TikTok from "Đăng bài" too. "Đăng bài" › TikTok (any video) has
    copy buttons, the cart's products, a checklist, "Đăng lên TikTok" (one of the member's own connected
    TikTok accounts, "Nháp" by default or "Đăng thẳng" with a privacy level and the note that until TikTok
    approves the app only "Chỉ mình tôi" on a private account works; disabled without an MP4 or while a job
    runs) and "Đã đăng tay" (one of the member's TikTok accounts and the post's link), with the posts below:
    one sent through the API is tagged "Nháp TikTok" or "Đăng thẳng" (and "Đang gửi" until TikTok has it), and
    once it is on TikTok its sender gets a box to paste its link. On a Facebook video the cart line instead says its
    products are Shopee's, the cart is set in TikTok's app, and "Tạo bản TikTok" gives TikTok its own script;
  - "Đăng bài" in the MP4 card, on every video, opens one drawer whose tabs are the platforms the MP4 may go to, each
    with how many posts it has ("YouTube Shorts (1)"), opening on the video's own platform (on Facebook when a
    suggestion's "Đăng" opened it): Facebook (below, with "Thêm vào hàng chờ" under its form; the drawer's own "Đăng"
    button belongs to this tab only), TikTok (above), YouTube Shorts and Instagram Reels (the app has no connection
    to either: "Tải MP4", "Copy caption + hashtag", then the post's link and "Ghi bài đã đăng", with the posts below
    and a delete for the member who recorded each). Under the MP4, "Bài đăng của video" lists the posts on every
    platform: TikTok's and the hand-recorded ones as a line with "Xem bài", Facebook's with their actions. On
    `/videos` a card says "+ TikTok, YouTube" beside its platform when its own MP4 is out elsewhere, and a Facebook
    video already on TikTok is not offered a TikTok version;
  - Facebook in "Đăng bài": the Fanpage, each shown as "<Page>, <its owner>" (a sole Page is chosen by itself), "Đăng ngay" or "Hẹn giờ" (at least 15 minutes
    ahead, within 29 days, typed in Vietnam time whatever the browser's time zone; after a post it is back on "Đăng ngay").
    A video of the 30-day plan opens on "Hẹn giờ" at the time the plan suggests (its day, at the group's posting
    time for its place in the day), said under the field. Its "Đăng" is disabled while the MP4 is out of date or the Page holds this
    very MP4, and it warns when the Page keeps an older post of the video. The pinned comment stays manual;
  - the "Bài đăng của video" card lists every post, newest first: its status, Fanpage, who posted it,
    the scheduled time or "Xem Reel", who cancelled or deleted it and when ("trên Facebook" when a check
    found it so), with "Kiểm tra" for a post on Facebook (reads it again after a change in Meta Business
    Suite), "Hủy đăng" for a post not yet public and "Xóa" for a public one, each with a confirmation,
    and a public post's numbers as on "Bài đăng" (without "Cập nhật view");
  - "Nhân bản", "Hủy" for a queued job, "Thử lại" for a failed one, "Xóa".
- **Kho kiến thức** (`/knowledge`): two columns (stacked on a phone). On the left, the card "Nhóm
  chủ đề": a field and "Thêm nhóm" (the new group is opened), then one line per topic group with its
  video count and "Chưa có prompt" when it has none; the chosen line is highlighted, the first group
  is chosen on arrival. On the right, the chosen group: its name as a heading with how many videos use
  it, the name field with "Đổi tên", and "Xoá nhóm" (disabled while the group has videos). Groups
  opened once stay loaded, so unsaved text in one survives opening another. A new group starts
  empty, and "Tạo video" cannot pick a group without a script prompt. The group is chosen in "Tạo
  video"; a clone keeps its source's group. Two tabs: "Prompt và từ cấm" (the script prompt and the
  clone prompt, each with "Lưu" and "Khôi phục mặc định", and beside them on a wide screen the banned
  words with "Lưu từ cấm", then "Gợi ý tìm ảnh" with "Lưu gợi ý"), "Kế hoạch 30 ngày" and "Backlog" (with its count; an idea of a day dropped on
  the tab's name goes to the Backlog):
  - start date ("Hôm nay là ngày N/30"), ideas per day (3–5), "Giờ đăng" (1–5 times, as tags), "Đã làm
    X/Y ý tưởng" with a bar, and a strip of 30 small cells, one a day (Trống, Có ý tưởng, Đang làm, Đủ
    video, Đã lên lịch đủ; today outlined), each a link to its day;
  - "Tiến độ verdict: đã làm X/Y video" with the target to change or clear ("Xóa mục tiêu"), or the
    target to set; it only counts, the line under it says the verdict is still decided in a meeting;
  - "Nhập file JSON/CSV" and "Tạo bằng AI", both ending in a preview table with errors (which block
    saving) and warnings; the plan is replaced only by "Lưu kế hoạch". An AI plan waits as a draft
    ("Xem trước" / "Bỏ") until then; a failed one shows its error;
  - "Prompt kế hoạch", folded, with "Lưu" and "Khôi phục mặc định";
  - above the days, filters for the session only: status, pain group (A–Z) and a search over topic,
    pain group, pain and hook that ignores accents ("sau benh" finds "Sâu bệnh"), "X/Y ý tưởng khớp",
    "Xóa lọc", and "Đầy đủ | Gọn" (kept in the browser as `plan-compact`; a compact card shows its
    title, status, numbers and buttons, and opens on its title or arrow);
  - the 30 days on one page, one card each (its date and weekday once a start date is set, "Hôm nay"
    in orange on today's, a line counting its shown ideas by status, "Không có ý tưởng khớp" when the filters
    hide them all), each idea with a 3 px left border in its status colour, its topic, pain group,
    pain and hook editable in place (saved when the edit ends), a status tag (Ý tưởng, Đã tạo video,
    Đã viết kịch bản, Xong, Đã lên lịch, Đã đăng) with the post's time, "Dự kiến đăng <time>" while
    no post is set, "Tạo video" or "Mở video", "Chuyển về Backlog" and "Xoá", and under them one line
    per Facebook post with its 48-hour numbers ("<Page>: N view, N share, share/view x,xx% đạt/không
    đạt 0,2%, N× trung vị", bold from 10×; "chưa đủ dữ liệu" under 5 measured posts; "chưa đo 48h"
    before). "+" adds an idea (greyed out at 5); dragging an idea onto another day moves it there. A
    day with 1–2 ideas says it should have 3–5. "Mở Backlog" opens the Backlog beside the days, to drag
    ideas between them;
  - the "Backlog" tab: "Thêm ý tưởng", "Nhập file JSON/CSV" (a file needs no day column; the preview's
    "Thêm vào Backlog" adds every idea, skipping topics already in the plan), a search and a pain-group
    filter, and the ideas as cards with "Xếp vào ngày…" (a full day cannot be picked).
- **Video editor** idea card: a video made from a plan idea shows "Theo kế hoạch 30 ngày, ngày N" (or "Backlog")
  with its pain group, pain and hook under the title.
- **Cài đặt › Máy render** (`/settings/render-nodes`): a switch "Render và cảnh động chạy trên máy render" with what
  it changes, a warning when it is on and no machine is running (with the number of jobs waiting); the machines with
  "Đang chạy"/"Đang tắt" and when each was last seen, "Xoá" (confirmed); "Thêm máy" takes a name and shows the
  PowerShell command with the token once, copyable. On a video page a waiting job reads "Đang chờ máy render: …"
  with "Hủy", and "Máy render đang dựng: …" while a machine renders it.
- **Kho tư liệu** (`/media`): "Thêm tư liệu" picks the product being made (approved affiliate products), which names
  the folder and the searches; a dashed drop zone takes a whole folder or many files ("Chọn thư mục", "Chọn file"),
  uploading one by one with a progress bar; under it the name with "Ảnh không nền", "Ảnh Google" and "Clip TikTok",
  which open the search in a new tab, and a box where pasting adds at once: a photo copied with "Sao chép hình
  ảnh", a link, or a "data:" address (Google Ảnh's thumbnails); a photo dragged from another tab can be dropped on
  it too. The primary "Dán ảnh / link", first in that row, adds whatever the clipboard holds in one click (the browser
  asks once for permission); "Thêm link đã gõ" sends typed links. The library below filters by folder, Ảnh/Clip and name, as tall cards (a clip with its seconds) with "Xoá"
  (videos that used it keep their copy). On a scene card, "Kho tư liệu" opens the same search and library in a
  dialog, on the folder of the product attached to the video (else its topic); "Dùng" copies an item into the scene,
  asking first when it replaces a picture.
- **Thư viện nhạc** (`/music`): the team's tracks with a player, topic and mood tags, source/license
  note ("Chưa ghi nguồn" when empty), who added it and when; filters by topic, mood, and name;
  "Tải nhạc lên" (MP3 up to 20 MB, then name, topics, mood, and source), "Sửa", "Xoá" (videos that
  used the track keep their copy). The topics to choose and filter by are the groups of Kho kiến thức, in its order,
  then "chung" (a hint under the field says so).
- **Affiliate** (`/affiliate`), a line saying what the page is for, then three tabs:
  - "Video đã đăng": filters over the loaded videos: tabs with counts ("Tất cả", "Chưa gắn sản
    phẩm", "Đã gắn", "Cần xem lại" for a video with a product that lost its approval or no longer
    meets the rules), "Tìm theo tiêu đề video" and "Mọi nền tảng" (Facebook or TikTok); the counts
    follow the search and platform, and "Không có video nào khớp" when nothing matches. Then
    Facebook reels and TikTok posts made by hand, newest first, each tagged with its
    platform, with the script's suggestions, a picker of approved products of the video's platform
    (labelled with the expected commission per order), and for a reel a copy button for the pinned
    comment with one link per product ("Gắn giỏ trong app TikTok" for TikTok). A product that lost its
    approval or no longer meets the rules stays attached with a yellow tag, and its link is left out of
    the copied text;
  - "Sản phẩm": products ranked by expected commission per order, with their platform tag ("Tìm qua
    API" for those Shopee's search found), shop, type, rating, sales, price, and status; filters by name
    or shop, topic group, platform and status; "Thêm sản phẩm" opens a drawer with two tabs, "Dán link
    Shopee" (a topic group and one link per line, up to 50; the rest is read from Shopee, so it needs a
    Shopee account with App ID somewhere in the team and says so when there is none) and "Nhập file"
    (Shopee Affiliate's "Lấy link hàng loạt" CSV dropped in; rows left out are listed by number, and
    without an App ID the drawer says stars, sales and shop type are still to fill in); "Nhập file" on
    the toolbar opens that tab. "Nhập tay" at the bottom opens the full form ("Nhập tay sản phẩm",
    platform first; the link is optional for TikTok Shop). A row being read shows "Đang lấy thông tin từ
    Shopee…" and the list follows it every 3 seconds; one that could not be read shows why in red, with
    a "Lấy lại thông tin" button. A Shopee draft whose stars, sales and shop type nobody has read (a row
    of the file, or a link, with no App ID in the team) says they are to be filled in by hand, links its
    Shopee page, and takes the three on the row itself (shop type, stars, sales, "Lưu"; the same save as
    "Sửa"), so it can be approved without opening "Sửa" for each one. "Sửa", "Xoá", "Duyệt", "Bỏ duyệt",
    "Xuất CSV". Rows ticked in their checkbox (only those the filters show) can be approved together with
    "Duyệt đã chọn" (those not meeting the rules stay drafts and are counted in the message), deleted
    together with "Xoá đã chọn", after a confirmation, or cleared with "Bỏ chọn". A row that fails the rules shows why,
    in yellow;
  - "Video đã đăng" also filters by product ("Lọc theo sản phẩm", "Mọi sản phẩm"): the products
    attached to at least one video, each with how many, most used first; picking one shows only the
    videos it is attached to;
  - "Doanh thu": the signed-in member's own Shopee orders over 7, 30 or 90 days, with totals and one
    row per video and Page; nobody else's.
- **Cấu hình › Tài khoản affiliate** (`/settings/affiliate-accounts`): the member's own Shopee
  accounts (App ID, the Secret's last characters, "Kiểm tra kết nối") and TikTok accounts (profile
  link, and the TikTok connection: "Đã kết nối @username, còn hạn tới …" with an avatar and "Ngắt
  kết nối", "Chưa kết nối TikTok" with "Kết nối TikTok", or a warning with "Kết nối lại" when TikTok
  refused a refresh), with "Đang dùng", "Sửa" (an empty Secret keeps the saved one) and "Xoá";
  "Kết nối TikTok" (TikTok's consent page, then back here with a message; the account is found by
  the TikTok username or made from it) and "Thêm tài khoản" are in the tab's header.
- **Quản lý Page**: each Page card says whose it is ("Thuộc: <member>"). Its owner sees "Thuộc: bạn"
  and the Page's Shopee account, picked from their own; a Page that belongs to nobody has "Nhận Page
  này". A Page is not handed to another member from the app. Only the owner sets the Page's topic
  group and posting times and reorders its queue; others read them as a line.
- **Đăng bài**, a menu group. Nothing is posted or approved here: a member reviews and posts a
  video from "Đăng" on its page; "Bài đăng" only retries a failed post.
  - **Bài đăng** (`/posts`): a table with one row per video, so a video posted to two Pages or
    posted again shows its title once. The row has the video's thumbnail (the title scene, or the
    pale tile) and title, which open the video, "N bài đăng" with its Pages, one status tag per
    status among its posts ("Đã đăng 2" for more than one), its total views and its latest time. Clicking the row opens its posts: the Fanpage with "Người đăng" under it; the time in Vietnam time, with who cancelled or
    deleted it and when under it ("Hủy: …" or "Xóa: …", "Trên Facebook" when a check found it so);
    "Đang đăng" (its publish job is still to run), "Thất bại" (red, with the job's reason under it in
    red, cut to one line with the whole reason in a tooltip), "Đã hẹn lịch", "Đã đăng", "Đã hủy" or
    "Đã xóa"; the views; then the same four icon buttons on every post, each with a tooltip: "Xem
    Reel" (opens the reel once public), "Thử lại" (sends a failed post's job again), "Kiểm tra", and
    "Hủy đăng" or "Xóa" with a confirmation. A button that does not apply to the post is greyed out,
    its tooltip saying why ("Video đang chạy một việc khác (xem Job logs)…" while its video has a job),
    so the buttons line up from row to row. There is no grid here: posts are read
    as numbers, and "Video" keeps the grid for working on videos.
    A post's views stay on one line so rows stay short: the views (or "Chưa có view"), a yellow
    warning icon when the last reading failed, and an icon-only "Cập nhật view" button, which asks
    for a new reading and spins until the numbers arrive. Opening the page asks the same by itself for
    the posts of the last 14 days not read in 15 minutes, so their buttons spin without a click. Shares, comments and reactions ("—" for
    one Facebook does not give), when they were read ("Đo lúc", Vietnam time), the 48-hour views
    with "Gấp N× trung vị Page (…)" or "Chưa đủ dữ liệu để so trung vị" and the share/view, the
    "Chưa có số view, app tự đo sau khi đăng 1 giờ" note and the failed reading's reason sit in
    tooltips, with "Xem TB N giây (N %), tiếp cận N" when Facebook gives them. A cancelled or deleted
    post's last reading is history, not bold: "Lúc xóa: N view (đo lúc …)" (or "Lúc hủy"), its failed
    reading said in words ("Lần đo cuối lỗi: …"), and its views add nothing to the video's "Tổng view"
    and sort after every live post's. The video's page
    shows the same numbers in full, with share/view green at 0,2 % or more, yellow under it. A post
    with numbers has "Phân tích" (an icon button on "Bài đăng", a button on the video's page). It
    opens "Phân tích bài đăng": views, average watch with its share of the posted length, reach,
    first plays, replays, total watch time, follows, shares, comments and reactions ("—" for one
    Facebook does not give); the retention curve ("Giữ chân người xem") over the reel, with a band
    and label per scene of the posted MP4; and a table per scene (time, share still watching when
    it starts, share lost during it), the scene losing most marked "mất nhiều nhất" in red. A post
    made before scene marks were kept shows the curve without the table, saying why. A reel with no
    curve yet says Facebook has none yet. Above the table, "Hiệu quả tuần này (từ T2 dd/mm)" (weeks start on Monday, Vietnam
    time) with an ⓘ whose tooltip says every figure is taken 48 hours after posting, so posts are
    compared at the same age. Then three cards with a light border and shadow (stacked on a
    phone), each with an icon in a pale orange square, its name and a grey line saying what it
    means, the figure large, and "Tuần trước: …" at the bottom with a green ↑ or red ↓ when this
    week is above or below: "Bài đã đủ 48 giờ" (posts of the week with their 48-hour numbers), "View
    phổ biến / bài" (the median: what an ordinary post reaches) and "Bài được chia sẻ tốt" ("N bài", with the share of posts at ≥ 2
    shares per 1.000 views beside it). No figure is a bare "—": an orange line under it says why ("N
    bài đang chờ đủ 48 giờ, sớm nhất …", "Chưa có bài nào đủ 48 giờ"), and the first card adds the posts still on their way. Under the cards, while a
    Page has fewer than 5 measured posts in 60 days, a line per such Page with a 5-step bar ("2/5
    bài") says how far it is from a median its posts can be compared with ("Gấp N× trung vị Page").
    Between the KPIs and the table, two cards side by side (stacked on a phone), each listing up
    to 5 videos with "Xem thêm": "Sẵn sàng đăng (N)", rendered videos whose MP4 is current and that
    have no live or scheduled post, oldest first, each with "Đăng", which opens the video with its
    "Đăng video" dialog already open (`?publish=`); and "Nhân bản (N)", Facebook videos that did well
    (a post reached its Page's usual 48-hour views, or the Page has too few measured posts to say)
    and can still be made again, most viewed first, with what each lacks ("chưa có bản TikTok",
    "chưa có trên <Pages>"). Its "Nhân bản ▾" button opens a menu of what is left: "Bản TikTok" when
    there is no TikTok version (`?clone=tiktok`), "Bản cho Page khác" when there is no Facebook clone
    yet and a working Page lacks it (`?clone=page`, the clone drawer with a variant request filled
    in). The request is dropped from the address at once. The same MP4 is never suggested for
    another Page. An empty card says so, and that a variant for another Page needs at least two Pages
    in use. A post updates
    by itself once the worker has done it. The list's filters sit on its own card, under the KPIs and
    the suggestions, which they do not filter (the one page whose filters are not under its title): status
    tabs with counts across the card's top, "Đang hoạt động" (the default: on its way, failed, scheduled
    and published), "Đã đăng", "Đã hẹn lịch", "Thất bại", "Đã hủy/xóa" and "Tất cả"; under them "Tìm
    theo tiêu đề", the Fanpage filter ("Mọi Fanpage") and, at the right, "Sắp xếp" ("Giờ đăng mới nhất",
    the default, or "Nhiều view nhất", posts not read yet last; videos follow their first post). The
    counts follow the search and Fanpage filters. They filter the posts and keep the videos that still
    have one. A tab leaves the other posts out
    of the rows and their tags. "Không có bài đăng nào khớp" when nothing matches a filter, "Không
    có bài nào đang hoạt động" when only cancelled or deleted posts are left. "Danh sách" and "Lịch",
    at the right of the title, switch between the table and the calendar on the same page.
  - **Lịch** (`/posts?view=calendar`; `/calendar` redirects there), after the content calendar of
    Meta's creator dashboard: a title naming the range ("2–8 tháng 11, 2026", "Tháng 11, 2026",
    "Thứ tư, 4 tháng 11, 2026") over "Giờ Việt Nam" and the legend (a dot for "Đã hẹn lịch" and
    "Đã đăng"); on the right "◀ Hôm nay ▶" and "Ngày | Tuần | Tháng" (Tuần by default, the choice
    remembered in the browser). Tuần and Ngày are hour rows (opened at 06:00): in each hour the first
    reel is its cover with its time and views on it and "+N bài khác" for the rest; a day shows every
    reel of the hour side by side. Tháng shows each day's first two reels as a small cover with "N
    lượt xem" ("Hẹn 20:00" while scheduled) and "+N bài khác". Choosing a reel, an hour or a day opens
    a drawer, "Bài đăng ngày dd/mm/yyyy" (with the hour when one was chosen), listing each post's
    cover, title, time and Page, status and views, with "Mở video" and "Xem Reel". Everything is in
    Vietnam time whatever the browser's time zone: the hour and day a reel sits under, the week and
    month it opens on, and today's mark. On a phone the month is compact, with a dot on each day that
    has a video; tapping a day opens the same drawer.
- **Job logs** (`/jobs`): every job, newest first, refreshed every 5 seconds. Filters over the loaded
  jobs: a search by video title first, a status Segmented with counts ("Tất cả", "Đang chạy" (waiting or
  running), "Lỗi", "Xong"), "Mọi loại" and "Mọi người" ("Không có job nào khớp" when nothing matches).
  Each row: the video title with its kind and job number under it, a status tag with an icon, who
  started it, start with the duration under it, AI call count with the model that wrote a script
  ("DeepSeek · deepseek-chat") under it, and the error on up to two lines. A row opens its video.
- **Cài đặt**, a menu group, last in the sidebar, with one page: **Cấu hình** (Pages moved out to
  **Quản lý Page**, its own menu item under "Video", since a Page's queue is daily work).
  Cấu hình (`/settings`, opening its first tab) is one page titled "Cấu hình" with four tabs, each
  its own address so a link or a reload keeps the tab; the menu keeps "Cấu hình" selected on all four.
  From 1200 px the tabs are a list down the left (240 px, staying in view), each with its icon and a
  line on what it holds ("Video mới bắt đầu thế nào", "AI viết kịch bản", "Kho ảnh, ảnh AI, giọng
  đọc", "Shopee và TikTok của bạn"), beside the tab; narrower, a row above it. Every tab starts the
  same way ([SettingsBlocks](../web/src/components/settings/SettingsBlocks.tsx)): its name, a line on
  what it sets, and its main actions on the right; a tab's groups each have a heading and a line.
  The content takes the whole width beside the list:
  - **Thiết lập mặc định** (`/settings/defaults`, the first tab): the same three cards as
    a video's "Thiết lập" tab plus the music level, and "Nhạc nền mặc định" under "Âm thanh" (the chosen
    library track with its player, "Chọn từ thư viện" / "Đổi bài" opening the library picker, "Bỏ nhạc mặc định";
    a track deleted from the library since says so in yellow), from 1600 px "Âm thanh" and "Hình ảnh" down the
    left and "Chữ & phụ đề" on the right, one column below that; read-only until "Chỉnh sửa" (in the
    tab's header, with "Huỷ" and "Lưu" while editing). While editing, the
    changes stay on the page ("Có thay đổi chưa lưu") until "Lưu" sends them together ("Đã lưu mặc
    định") or "Huỷ" drops them. They apply only to videos created afterwards.
  - **Mô hình AI** (`/settings/ai`): "Đang dùng để viết kịch bản" picks the team's provider (a
    provider not set up yet is greyed out, "chưa cấu hình"); from 1600 px it sits on the left,
    staying in view, beside the providers. Below or beside it, one collapsible line per
    provider with "Đang dùng", "Sẵn sàng" or "Chưa cấu hình" and its model; the one in use is open.
    Opened: "API key" (pasted once with "Lưu key", then shown as "Đã lưu, kết thúc bằng …abcd" with
    "Dán key mới" and "Xoá key"; Claude without a saved key says it uses the server's `.env` key),
    "Base URL" (empty means the default shown as placeholder), "Model" (typed, or picked from the
    names "Kiểm tra kết nối" fetched), then "Lưu", "Kiểm tra kết nối" (enabled once saved) and
    "Dùng để viết kịch bản". What still stops a provider is shown in yellow under its fields.
    Under the provider choice, the card "Giọng đọc VieNeu" ("Sẵn sàng" / "Chưa cấu hình") takes the VieNeu API key the
    same way ("Lưu key", "Dán key mới", "Xoá key") with a link to VieNeu's developer page; with a key, VieNeu's
    voices join the "Giọng" picker. A service whose voices cannot be listed is named in yellow under the picker.
  - **Nguồn tư liệu** (`/settings/sources`): two groups, "Kho ảnh và video miễn phí" and "Dịch vụ AI". "Kho ảnh và video miễn phí": first the switch "Tự tìm ảnh sau khi viết kịch bản"
    (on by default: a stock photo for every scene once a script or clone is written) with "Thứ tự
    tìm: Pexels → Pixabay → Openverse" (the sources in use); then the stock libraries side by side
    (Pexels, marked "Mặc định", and Pixabay: photos and clips; Openverse: photos, no key), each
    with "Sẵn sàng" or "Chưa có key", a switch (titled "Hiện trong hộp chọn") that hides a source
    from the picker and "Tìm ảnh" for the whole team, and its API
    key (pasted with "Lưu key", then "Đã lưu, kết thúc bằng …abcd" or "Đang dùng key trong file .env
    của máy chủ", with "Dán key mới", "Xoá key" and a "Lấy key" link); below, "Nguồn ảnh AI mặc định"
    ("Cloudflare (miễn phí)" | "Gemini (tốn phí)"), which every "Tạo ảnh AI" button uses, and
    "Phong cách ảnh AI" (the text added after every scene's prompt, "Lưu phong cách", "Dùng mặc
    định" once edited; empty adds nothing) in the first card of "Dịch vụ AI", then its keys side by
    side (three across from 1600 px): Cloudflare (a Workers AI API token) and Gemini, each with its
    model and "Mặc định" on the default one, and ElevenLabs, the narration key. A
    missing or rejected ElevenLabs key is shown on the voice picker with a link "Mở Nguồn tư liệu".
  - **Quản lý Page** (`/fanpages`, its own menu item under "Video", outside Cài đặt): a line of counts (đang
    dùng, lỗi kết nối, ngừng dùng), then a small card per Page in use, broken ones first, in a grid
    that fits as many cards of at least 320 px as the width allows. A card shows the Page's initial,
    its name linking to the Page's dashboard, its id and the token's last four characters, and a tag:
    "Hoạt động", "Lỗi kết nối", "Đang kiểm tra…" or "Chưa kiểm tra". A broken Page has a one-line
    pale band with the reason, the scheduled posts it puts at risk and "Dán token mới". Four numbers
    in one row: followers (with this week's gain), views, reach and engagements of the last 7 days;
    under the owner line one grey line on posting: its topic group, its posting times and "N video
    trong hàng chờ" (all of it is on the dashboard's "Lịch đăng" tab);
    then a footer line with when it was last checked and the icon button "Kiểm tra ngay". A click
    anywhere on the card but its controls opens the Page's dashboard. Opening the page checks by itself the
    Pages not checked in 15 minutes. The "⋯" menu has "Mở trên Facebook",
    "Dán token mới", which must reach that Page, and "Ngừng dùng" (confirmed). Stopped Pages are
    folded into "Đã ngừng dùng (N)" at the bottom, each with its post count, "Dùng lại", and "Xóa"
    for one that never had a post (confirmed; it removes the token and the numbers); for one with
    posts "Xóa" is greyed out with why. "Thêm Fanpage" takes a token, "Kiểm tra token" lists the
    Pages it manages (a sole Page is ticked, one it cannot post to is greyed out), and "Lưu" keeps
    the chosen ones. A stopped Page cannot be posted to.
  - **A Page's dashboard** (`/fanpages/[id]`, modelled on Facebook's Professional Dashboard, built from what the
    app already reads): "← Quản lý Page" above the Page's name; at the title's right "7 ngày / 28 ngày / 90 ngày"
    (28 at first) and "Kiểm tra ngay"; a grey line naming the period (Vietnam time, today included) and that each
    number is set against the same number of days just before. Every figure is a tile: its name (an ⓘ tip where
    the number needs one), the value, and "↑ 12% so với 28 ngày trước" in green or "↓" in red, the arrow always
    there so the direction is not colour alone; "Chưa có 28 ngày trước để so" when there is nothing to compare.
    Daily charts are one orange line over a pale area, a gap where Facebook gave no number, a crosshair and a
    tooltip with the day and value on hover, and "Xem bảng" for the numbers as a table. Six tabs:
    - **Tổng quan**: tiles Lượt xem, Tiếp cận, Tương tác and Người theo dõi mới ("Hiện có N"); the daily views
      chart; "Bài đăng mới nhất" (cover, title opening the video, when it went live, its views, reach, reactions,
      comments, shares, average watch time and when they were read); "Đã lên lịch, 7 ngày tới" (the next six of
      the week's scheduled posts and free posting times, in time order, "Khung trống" for a free one); "Kết nối"
      (the token's status, its last check, and a Page Insights error if any).
    - **Lượt xem**: tiles Lượt xem, Tiếp cận and Thời gian xem TB (the average watch time of the period's posts,
      weighted by their views); the daily chart, switched between views and reach, with a "Hoạt động đăng"
      switch (on at first) that puts a grey dot under each day the app posted, and the period's post count.
    - **Tương tác**: the Tương tác tile and its daily chart, then Cảm xúc, Bình luận and Chia sẻ summed from the
      latest reading of the period's posts, each with a tip saying it is approximate.
    - **Đối tượng**: Người theo dõi mới and the current count, and the followers chart.
    - **Nội dung** (like Facebook's content library): a card titled "N bài app đăng trong 28 ngày" with "Cột"
      and "Xuất CSV" at its right, then a table, one row per post the app made to the Page that went live in the
      period: the post (cover and title opening the video, kept at the left when the table scrolls sideways), Lên
      lúc, Trạng thái ("Đã đăng", or "Đã gỡ" with when in its tip), then the latest reading's Lượt xem, Tiếp cận,
      Cảm xúc, Bình luận, Chia sẻ, Theo dõi and Xem TB, View 48 giờ and So với trung vị ("↑ 1,3×" in green from
      the median up, "↓ 0,6×" in grey below, the arrow always there; "—" while the Page has too few measured
      posts), numbers right-aligned in even-width figures, a ⓘ tip on the headers that need one. Every column
      but the post sorts by a click on its header (newest first at first; a missing number sorts last). "Cột"
      ticks the columns shown, remembered in this browser. "⋯" at the row's end: "Mở video", "Mở reel trên
      Facebook" (greyed out once taken down) and "Cập nhật view" ("Đang đo view…" while the worker has not read
      it; the table asks again every few seconds until it has). "Xuất CSV" saves the rows in their shown order
      with the shown columns, the title first and the reel's link last, UTF-8 for Excel. A grey line under the
      table says the numbers are the latest reading, that posts made outside the app are not there, and the
      Page's 48-hour median (or how many measured posts it needs). Over 50 rows the table pages by 50; none says
      "Chưa có bài nào app đăng lên Page này trong N ngày."
    - **Lịch đăng**: "Đăng theo lịch" (as it was on the card): the topic group the Page posts and its posting
      times (tags such as "20:00", typed or removed with ×; "Dùng giờ của nhóm" goes back to the group's), a small
      line saying whose times they are and the next three free times within 48 hours ("và N khung khác" for the
      rest), then "Hàng chờ (N)": each waiting video's number, cover, title (opening the video), who added it
      and when, the reason in yellow when it could not be scheduled, "Lên"/"Xuống" for the owner and a bin ("Bỏ
      khỏi hàng chờ", confirmed); an empty queue says how to add one. Beside it the whole week of scheduled
      posts and free times.
    Numbers Facebook does not give are not shown (followers against non-followers, content types, traffic
    sources, unfollows, 3-second and 1-minute views). An unknown Page shows "Không tìm thấy Fanpage".

Phones (below 992 px wide; built):

- The menu collapses into a drawer opened from a header, which shows the logo and the avatar
  only. On a wider screen there is no header: the sidebar stays in place while the page scrolls,
  with the member's name and account menu (Đổi mật khẩu, Sửa tên, Đăng xuất) at its foot. The page
  beside it has no maximum width: on a large screen tables and cards fill the window, and only
  paragraphs of grey explanation stop at about 820 px so they stay readable.
- In the video editor the actions ("Nhân bản", "Xóa") wrap under the title, the tab panel sits
  under the scenes, the render bar stays at the bottom of the screen, and each scene's preview is
  a centred thumbnail at most 220 px wide.
- Tables keep their columns and scroll sideways inside their card; the page itself never scrolls
  sideways.

Planned:

- **Knowledge Base documents:** edit each document and trigger "AI soạn nháp" (AI draft); the food
  bank table with draft or approved status and source links; approve rows.

## Video Template

One template, derived from the reference channel (see [content.md](content.md#video-formula)),
with named presets a video can switch (its "Thiết lập" tab, defaults on Cài đặt › Thiết lập mặc
định). The defaults below are the original template; [Presets](#presets) lists the others.

- **Frame:** 9:16 vertical, 1080×1920 at 30 fps. Photos are cover-cropped from the centre, with
  no black bars.
- **First frame = thumbnail** (and the cover of a reel the app posts to Facebook):
  - a close-up food photo filling the frame, with vivid color;
  - the chosen title in a text box centred in the frame, 3–5 lines, with no fade-in.
- **Text box:** a scene whose text is empty has none, so a video can mix scenes with and without
  text, or carry no text at all. An empty title scene leaves the thumbnail without a box, and the
  video is listed under its topic.
  - yellow background (`#FFD60A`) with black text (`#111111`). Outlined text without a box was
    rejected as the default because it is hard to read on bright photos; it is offered only as the
    opt-in "Không hộp" preset below;
  - bold, centered, at most 960 px wide; uppercase by default. "Dạng chữ" on a video's Thiết lập
    (and on Cài đặt › Mặc định video) keeps the text as typed instead, for the content scenes and
    their text layers, and on its own for the title ("Dạng chữ tiêu đề"); the red marked words keep
    their colour either way, and the editor's previews are drawn the same way;
  - keywords marked `*...*` are drawn in red (`#E10600`);
  - long text wraps and shrinks, and is rejected only if it still does not fit: the title starts
    at 96 px and shrinks to 64 px (at most 5 lines); body text starts at 84 px and shrinks to
    60 px (at most 3 lines).
- **Body scenes:**
  - one item per scene, 3–5 seconds each (the renderer accepts any length of 1 s or more);
  - the item name plus one benefit line, separated by a manual line break;
  - text box in the lower third, with its bottom edge at y = 1440, clear of the food and of the
    platforms' caption and button area; a member may drag it elsewhere inside the safe zone (see
    "Vị trí chữ" above).
- **Motion:** every scene zooms in linearly around the centre, from 1.00 to 1.12. Scenes are
  joined by a 0.4 s crossfade centred on the boundary, so the total length equals the summed
  scene seconds.
- **Audio:** by default no music: the video has a silent track, and members pick music (from
  Claude's suggestions) inside TikTok or Facebook when posting, because those libraries cannot be
  used outside their apps and an uploaded copyrighted MP3 can get the video muted or demonetized.
  A member may add one MP3 per video, uploaded or picked from the team music library, at 25%
  volume by default, looped or cut to the video length with a 1.5 s fade-out.
- **Narration:** each scene's voice text, read in the ElevenLabs "Adam"
  voice, mixed at full level over the music, starting 0.2 s into the scene. A scene whose narration
  is longer than its seconds is lengthened to fit. The "Giọng đọc" card turns it off for the whole
  video. A scene with an empty voice text reads its on-screen text instead, and the editor shows
  what it will read; only a scene with neither is silent.
- **Font:** must render Vietnamese diacritics. The default is Be Vietnam Pro Black.
- **Length:** derived from the scene count. A title scene plus 5–7 scenes runs about 30–55 seconds with narration, which lengthens scenes to fit.

### Presets

Each video picks one of each ([reels_render/options.py](../worker/src/reels_render/options.py));
free colour or size sliders are not offered. A person watches a sample of each before they are
relied on (samples in the PR that added them).

- **Transition:** Mờ dần (the 0.4 s crossfade above), Cắt thẳng (hard cut; each scene is exactly its
  seconds), Trượt (the next scene slides in from the right over 0.4 s). The total length is the
  same for all three.
- **Cỡ chữ** (`text_size` for the content scenes, `title_text_size` for the title; on "Thiết lập" › Chữ and on
  Cấu hình › Thiết lập mặc định): Lớn (the original template: the largest font that fits, the title 96 down to
  64 px in at most 5 lines, a scene 84 down to 60 px in 3), Vừa or Nhỏ. Vừa and Nhỏ start from the font Lớn would
  choose ×0,82 and ×0,68, never below 54 / 44 px for the title and 50 / 42 px for a scene, and shrink further only
  to fit, so they are smaller even for a long title, and a text too long for Lớn may fit at a smaller size (the
  "Chữ tràn hộp" check follows the size chosen). Requested by members: a long title filled half the screen.
- **A scene's own effects** ([reels_render/effects.py](../worker/src/reels_render/effects.py)), set in the
  studio's "Chỉnh cảnh N › Hiệu ứng", content scenes only (the title opens the video and is its cover):
  the transition into the scene, one of Mờ dần, Cắt thẳng, Trượt sang trái, Trượt lên, Quét ngang, Phóng
  vào, Mở vòng tròn, Qua màu đen, Chớp trắng, Hoà tan, Nhoè ngang, Vỡ điểm ảnh ("Theo cả video" takes the
  video's); and a colour preset graded on the picture only, never the text box: Gốc (as shot), Tự nhiên,
  Tươi sáng, Rực rỡ, Điện ảnh, Xanh cam, Phim cũ, Phim mờ, Nắng vàng, Ấm, Lạnh, Đêm xanh, Trầm, Pastel,
  Đen trắng. Every transition takes 0.4 s around the boundary, so the length never changes; a Cắt thẳng among
  other transitions cuts 0.2 s before the boundary. The phone shows each with CSS, close to the MP4 but not
  the same (no curves or per-tone colour in CSS). A clip's speed (0,5× to 2×) is offered there too. Sample:
  [samples/hieu-ung.json](../samples/hieu-ung.json) shows every transition and colour.
- **Text and sticker layers** ([reels_render/layers.py](../worker/src/reels_render/layers.py)), content scenes
  only, any number per scene, each for its own seconds from its own second of the scene (cut at the scene's
  end), centred where it was dropped and kept inside the frame, on top of everything (captions included). A text
  layer: its words (`*word*` in the accent colour, line breaks kept), Chữ viền (white, black outline, yellow
  accent) or a box (Hộp vàng, Hộp đen, Hộp trắng, Hộp đỏ), Nhỏ / Vừa / Lớn. A sticker, drawn by the render core
  itself (no image files): Mũi tên xuống, Mũi tên phải, Khoanh tròn, Ngôi sao, Trái tim, Dấu tích, Dấu X, Nhãn
  MỚI, Nhãn HOT, Nhãn SALE, at 160, 240 or 340 px. Entrance: Hiện ngay, Mờ dần, Trượt lên (from 120 px lower),
  Trượt từ trái (from off the frame), each over 0.3 s and fading in. The studio shows the exact picture the render
  lays on. Sample: [samples/lop-chu-sticker.json](../samples/lop-chu-sticker.json).
- **Sound** ([reels_render/sounds.py](../worker/src/reels_render/sounds.py)), any scene, the title included.
  Sound effects made by FFmpeg itself (no sound files, so nothing to license): Vút, Lướt nhanh, Ting, Bụp, Tách,
  Bùm, Dâng lên, Hoàn thành, Sai rồi, Tiền về, Nhịp tim; each from its own second of the scene, at Nhỏ (×0,5), Vừa
  or To (×1,6), added over the music and narration. A scene's own music level: Tắt nhạc, Nhạc nhỏ (×0,4) or Nhạc to
  (×1,6), else the video's. "Bài nhạc bắt đầu từ giây" skips the song's intro for the whole video (0–600 s; past
  the end the song loops from its start). The studio plays the same sounds (the api makes them with the same
  filters) at their seconds, but a browser cannot play louder than full, so "To" and "Nhạc to" may sound like
  "Vừa" there. Sample: [samples/am-thanh.json](../samples/am-thanh.json), rendered with any music.
- **Mẫu dựng** ([autoedit.py](../api/src/reels_api/autoedit.py)): the effects above as rules for any video: the
  transitions into the content scenes in turn, one colour, sounds on every content scene and on the title, the
  title's music level, and layers on the last scene. "Gợi ý của app": Phóng vào, Trượt sang trái, Mờ dần, Quét
  ngang in turn, a soft "Vút" at the start of every content scene, a soft "Dâng lên" on the title, and "Lưu video lại
  *để xem sau nhé!*" sliding up near the top of the last scene. Applying a template replaces the transitions and
  colour and adds its sounds and layers (never the same one twice). A team template is saved from a video in the
  studio (its scenes' transitions, most used colour, the first content scene's sounds that has any, the title's
  sounds and music level, the last scene's layers). Cấu hình › Mẫu dựng lists them (rename, remove) and picks the
  one put on every new video as soon as its scenes are written (AI script, clone or "Tự viết"); none by default.
  "Tạo video" with "AI viết kịch bản" has the box **"AI gợi ý hiệu ứng"** (off by default): the AI then picks each
  scene's transition, colour, a sound and a few lines of text in the same call (see
  [content.md](content.md#script-generation-contract)), changeable in the studio like any effect.
- **Motion (photos only):** Zoom vào (the default), Zoom ra (from the zoom back to 1.00), Lia ngang
  (held at the zoom, travelling left to right), Đứng yên. **Độ zoom:** Nhẹ 1.06, Vừa 1.12, Mạnh 1.18.
- **Text box:** a team box style ("box": its box colour, opacity, text and keyword colours, copied
  into the video; with nothing chosen it is the yellow box) or Không hộp. Opacity: Đặc 100%, Hơi
  trong 88%, Trong 70%, Không nền (drawn exactly as Không hộp, the box colour as the outline's). The older presets below are no longer offered on the page and stay only so
  videos made with them render as before: Vàng (the default above), Trắng (white box, black text, red keywords), Tối (near-black
  box at 88%, white text, yellow keywords), Đỏ (`#E10600` box, white text, yellow keywords), Không
  hộp (white letters with a black outline 9% of the font size, yellow keywords). **Colours:** the
  text, the keywords and the box (the outline without a box) are each Theo kiểu (the style's own) or
  any colour, from a swatch or the picker; a custom box keeps the style's opacity (Tối stays 88%).
  Every colour is drawn as chosen: a pair below WCAG contrast 3 (text or keywords on their box or
  outline) only warns. Keywords on Theo kiểu take the style's keyword colour unless it is within
  RGB distance 100 of the text or below contrast 3 on the box, then the style's alternate (black on
  Vàng/Trắng, white on Tối/Đỏ, red without a box), then red, yellow, white or black. Near-black letters
  (luminance under 0.05) without a box get a white outline. The thumbnail and the scene previews are
  drawn in the chosen style and colours. **The title's look:** by default the title scene follows the
  choices above; it can instead have a look of its own (style, colours and opacity, the same choices
  as the scenes'), which wins over everything else. Videos made with the older "Kiểu tiêu đề: Hộp
  vàng" keep the original yellow box and black text on the title, whatever the scenes use.
- **Narration:** the voice (any of the account's ElevenLabs voices; the server's default otherwise),
  the speed (a tempo factor from 0.7 to 1.3 in steps of 0.05, applied with FFmpeg to the narration
  ElevenLabs returns; presets saved before the slider read as 0.8 / 1.0 / 1.2), the level (0–100%), and "Nhỏ nhạc khi có giọng
  đọc", which compresses the music under the narration (a sidechain, about a quarter of its level).
  Changing the voice or speed makes the narration again on the next render.
- **Captions (phụ đề theo giọng đọc):** content scenes with narration only, never the title scene.
  White bold 58 px text on a rounded black box at 67%, at most two lines and four words, centred
  just above the scene's text box (or with its bottom at y = 1440 when the scene has none).
  "Từng cụm" shows each phrase while it is read; "Từng từ" also lights the word being read in
  yellow. Phrases break after punctuation. The timing is an estimate spread over the narration by
  letters, not ElevenLabs' timestamps, so it can run slightly ahead or behind.

### Video Modes ("Kiểu video")

A video is one of two kinds, chosen in "Tạo video" (except "Từ video mẫu", whose scenes are cut from the sample)
and changed at any time on the video page's "Kiểu video" card, which asks first and says that every photo, clip
and "Ảnh món" is kept:

- **Slide ảnh** (the default, every older video): each scene over its own photo or clip, as below.
- **Video xuyên suốt:** one photo or clip, the title scene's, runs under the whole video ("5 công dụng của chuối
  xanh"). The title card says so; the content cards hide their picture, search terms and photo prompt, and show
  "Ảnh món trong cảnh này" instead. Scenes join by hard cuts and the text fades in and out (0.3 s), so the
  backdrop never jumps; a short clip loops from the title scene's "Bắt đầu từ giây". In the studio a content scene has
  no transition, colour or speed of its own. A scene that names a dish turns on its "Ảnh món": the scene's own photo,
  chosen with the scene's usual picture tools, framed over the backdrop (Bo góc, Tròn, Vuông, or Giữ nguyên for a
  cut-out photo; Nhỏ, Vừa, Lớn; Trái, Giữa, Phải, Dưới; and an entrance), dragged anywhere in "Xem trước". The
  preview plays the backdrop under every scene, as the MP4 does.

"Nghỉ sau lời đọc" (Thiết lập › Âm thanh: Ngắn 0,4 s, Vừa 0,7 s, Dài 1 s) is the pause after each scene's
narration for scenes whose seconds follow it; changing it changes those scenes' seconds at once.

### Video Scenes

Any scene, the title scene included, can use a short video clip instead of a photo. The clip
takes the photo's place in the frame. Everything else stays the same: the text box, its
position, narration, music, and the crossfade. Upload limits, storage, and render details are in
[architecture.md](architecture.md#scene-video-clips).

- **Editor:** the scene card has "Tải video lên" (MP4/MOV/WebM, up to 50 MB). A scene with a clip
  shows a muted looping player, a "Bắt đầu từ giây" field next to "Số giây", and "Xoá video".
  A scene has a photo or a clip, never both. Switching from one to the other ("Tải video lên" on
  a photo scene; "Tải ảnh lên" on a clip scene) asks first.
- **Length:** a new clip sets the scene's seconds to the clip's length minus the crossfades around
  it, at most 10 s. Members may
  change both fields. A scene longer than the clip left after its start holds the last frame for
  the rest of the scene and shows a yellow warning, "Video ngắn hơn cảnh, khung cuối sẽ đứng yên".
- **Title scene as a clip:** the hook box appears on the very first frame with no fade-in. The
  thumbnail and the title-scene preview are the clip's frame at the start time, so the first
  frame of the MP4 still matches the thumbnail. Members choose the start time so that this frame
  is a good still.
- **Motion:** a clip gets no Ken Burns zoom, because it already moves. Adding a zoom on top of
  camera motion looks shaky. Photo scenes keep their zoom, so a video can mix photo and clip
  scenes.
- **Sound:** a clip's own audio is always dropped. The soundtrack is only the music and narration,
  so nobody's camera noise or copyrighted sound ends up in the MP4.
- **Source footage:** vertical 1080×1920 at 30 fps renders best. Other sizes are cover-cropped
  from the centre, and other frame rates are converted to 30 fps (24/25 fps material may judder
  in slow pans, see [Smooth Motion Rules](#smooth-motion-rules)). Clips should be steady, without
  fast pans, and contain no text or watermarks.

### Food Pairing Template (planned)

This is a second template, for the [food pairing formula](content.md#food-pairing-formula-planned).
The reference was 720×1280. Here it is scaled to the 1080×1920, 30 fps frame.

| Segment | Layout | Default length |
|---|---|---|
| Hook | Full frame: B-roll of the main food (e.g. a vegetable garden) with the hook box; an uploaded clip renders as a [video scene](#video-scenes) | 2.3 s |
| Pairing 1…N | Split frame: B-roll strip on top, pair plate below | 3.5 s each |
| Bridge (between pairings) | Full frame B-roll | 0.8 s |

With 4 pairings, the total is 2.3 + 4 × 3.5 + 3 × 0.8 = 18.7 s. It ends on the last pairing,
with no bridge and no CTA.

- **Split:** the top strip takes the upper third (y 0–640) and the plate photo takes the rest
  (y 640–1920). The two meet at a straight cut with no border.
- **Plate photo:** shot top-down with a white plate on a wooden table, cover-cropped so that the
  food sits between y ≈ 760 and y ≈ 1400. The bottom ~25% (y > 1440) is hidden under the Facebook
  caption and buttons.
  - The panel is 1080×1280 (27:32), a portrait rectangle, not a square. Source photos should be
    4:5 (e.g. 1080×1350), which loses only about 70 px of height to the crop. A 1:1 photo must
    be scaled up to 1280 px high and then loses about 100 px on each side, which can cut off X
    (left) or Y (right) at the plate's edges.
  - The plate is not centred in the panel. The panel's centre (y = 1280) would push the lower
    half of the plate under the caption area. The plate sits in the upper half of the photo, with
    empty table below it.
  - The pair's image prompt therefore becomes "top-down, white ceramic plate on wooden table, [X]
    on left, [Y] on right, plate in the upper half of the frame, empty wooden table below, soft
    natural light, photorealistic, 4:5". Uploaded or stock photos follow the same framing.
- **Hook box:** the same yellow box with black, bold uppercase text in 3 lines, centred, in the
  upper third of the frame. Pairings and bridges carry no text.
- **Audio:** soft instrumental piano and no narration. The narration switch is off by default for
  this template.

### Smooth Motion Rules

The rules below keep motion and cuts smooth. The ones marked (built) describe the current
renderer ([graph.py](../worker/src/reels_render/graph.py),
[timeline.py](../worker/src/reels_render/timeline.py)). The rest are rules for the
pairing template and for later tuning.

- **Constant frame rate (built):** the output is 30 fps CFR. Scene lengths are rounded to whole
  frames cumulatively, so durations never drift. B-roll footage must be converted to 30 fps
  (`fps=30`) before use. Material at 25 or 24 fps should be avoided: converting it repeats
  frames, which shows up as judder in slow pans.
- **No zoom jitter (built):** photos are scaled to 2× the frame before `zoompan`, so its
  integer crop steps fall below one output pixel. Fine textures such as wood grain or a plate rim
  can still shimmer. The fix is a slower zoom or `PRESCALE = 3–4`, at the cost of render time.
- **Slow, steady zoom:** zoom by 6–12% over the whole clip, at a steady rate (linear today).
  Short clips need a smaller range: a pairing of 3.5 s should zoom from 1.00 to 1.06 at most,
  because a range that suits 5 s looks rushed at 3.5 s. The zoom must not restart within one
  continuous shot.
- **A continuous top strip:** across all pairings and bridges, the B-roll is one unbroken clip:
  a single input that is trimmed and overlaid, never restarted per segment. Only the plate below
  cuts. The eye then reads the cut as "the plate changed" rather than as a jump.
- **Match cuts:** every plate shares the plate, table, camera angle, light, and the plate's
  position in the frame (upper half, 4:5). Only the food changes, so a hard cut looks like a swap,
  not a jump. The AI image prompt stays fixed apart from `[X]` and `[Y]`. Stock photos with different angles are
  rejected for this template.
- **Cuts on the beat:** the pairing template uses hard cuts with no crossfade, as the reference
  does. When a track is chosen, each boundary snaps to the nearest beat within ±0.15 s, at whole
  frames. The total length may change by a few frames. A crossfade (built: 0.4 s in the default
  template) suits slow, full-frame photos. On a split frame it blurs the two plates together.
- **Loop-friendly ending:** the last pairing ends with a hard cut and no music fade-out. The
  built 1.5 s fade is turned off for this template, and the track is cut at a beat. When the
  platform loops the video, it then jumps straight back to the hook with no silent gap.
- **Hook on the first frame (built):** the text box appears with no fade-in, so the thumbnail and
  the first frame are the same.
- **Encoding (built):** libx264, `-preset medium -crf 20`, yuv420p, `+faststart`. For the
  platforms' second compression pass, CRF 18 and a 2 s keyframe interval (`-g 60`) keep motion
  cleaner after Facebook re-encodes the video. This should be measured before adoption.
