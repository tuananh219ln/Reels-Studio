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

## Screens

Built:

- **Login** and **user management**.
- **Tạo video** (on the video list): topic group, topic, and a line naming the provider and model
  that will write the script ("Viết bằng: … (đổi trong Cài đặt)"), in red with a link when that
  provider is not set up.
- **Video list** (`/videos`): thumbnail (the title-scene preview, or a grey tile with the title or
  topic), title, status (Nháp / Chờ / Đang viết / Đang render / Xong / Lỗi) with the labels "MP4
  chưa cập nhật theo bản sửa" and "Render lại lỗi", creator, date, search by title or topic,
  "Tạo video".
- **Video editor** (`/videos/[id]`), updating itself while a job runs and while teammates edit.
  The scenes fill the left column. The right column is a panel with three tabs, "Xuất bản" (the MP4
  and "Đăng Facebook"), "Thiết lập" (the video's own settings: narration and music) and "Nội dung
  đăng" (the post texts); until a member picks a tab it shows "Thiết lập" while there is no MP4
  and "Xuất bản" once there is. On a wide screen the panel stays in view while the scenes scroll.
  "Render" and "Tạo ảnh AI cho cảnh thiếu" sit in a bar stuck to the bottom of the screen, which
  counts the red reasons still blocking the render ("Còn N lỗi cần sửa") and scrolls to the first
  one when clicked, opening the scene that holds it. The editor has:
  - **View and edit mode**, for the whole page. A video already rendered or posted opens in view
    mode ("Xem"), so a stray click cannot change it: every scene field reads as plain text, and
    the title choice, scene move/delete/add, every photo and clip action, "Vị trí chữ", music
    and the "Thiết lập" tab are disabled. Still available: opening and closing scenes, playing
    previews and the MP4, "Tải MP4", "Nhân bản", "Xóa", "Render", the "Xuất bản" tab and the
    post texts under "Nội dung đăng" (they are not part of the video). "Chỉnh sửa" beside
    "Nhân bản" unlocks the page, shown by a blue "Đang chỉnh sửa" tag by the title and a blue
    outline round the scenes; fields still save one by one when left, so there is no "Huỷ".
    "Xong" saves the field being typed in and locks the page again, unless a save was refused
    (then a message points to the field). A video never rendered opens in edit mode. The mode is
    chosen when the page opens and is not stored;
  - **scene cards that open and close.** A closed card's title row shows a 40×40 thumbnail of
    the preview, "Cảnh N" (or "Cảnh tiêu đề"), its seconds, its text on one line (without the
    `*` marks) and a tag: red "N lỗi", yellow "N cảnh báo" or green "Sẵn sàng"; an open card
    shows the name, seconds and tag. A click or Enter anywhere on the row opens or closes it;
    the move and delete buttons beside it do not. When the page opens, a draft's scenes are all
    open; in a rendered video only the scenes with a red reason are. "Mở tất cả" and "Thu gọn
    tất cả" sit above the list. A closed card keeps its fields, so closing never loses text;
  - inside an open card, two columns (stacked on a phone, the picture first): the 9:16 picture
    with its tools on the left, the fields on the right: "Chữ trên màn hình" (a "?" beside it
    explains `*từ*` and line breaks), "Lời đọc", "Số giây" and "Bắt đầu từ giây" (clip only) side
    by side, "Từ khóa tìm ảnh", "Prompt ảnh 9:16" (content scenes), then the reasons and
    warnings. Under the text and the voice text a counter shows the words as typed (the `*` not
    counted), in yellow outside the script's lengths ([content.md](content.md): at most 10 words
    on a scene, 12 on the title; voice text 8–15 words, 8–12 on the title); it never stops a save;
  - **"Xem trước"** in the render bar, and "Xem từ cảnh này" (a play icon) on every scene card,
    play the video in the browser before any render, in a 9:16 dialog: each scene for its
    seconds (lengthened to fit its narration), the frame without text moving like the video's
    motion setting with the exact text box on top where the render puts it, clips from their
    start time, the video's transition (crossfade, cut or slide), the music from where that scene
    falls in the video (lowered while narration plays when ducking is on). Narration: the MP3 a
    render already made when the text has not changed since, else the browser's own Vietnamese
    voice (free, at the video's speed); a browser without one says so and those scenes stay
    silent. The covered areas of Reels / TikTok / Shorts (top bar, right button column, name and
    caption at the bottom) are shaded in red over the frame, the safe zone dashed; a switch hides
    them. Buttons: previous scene, "Tạm dừng" / "Tiếp tục" ("Xem lại" at the end), next scene,
    "Từ đầu". A note says it is close to the MP4 but not the MP4 (captions and the audio mix come
    only with a render). It is available in view mode too;
  - choose 1 of 5 titles (the card names the provider and model that wrote the script, "Kịch bản
    viết bởi …"); edit the title scene and every content scene (text with `*word*` in
    red, voice text, seconds, image prompt), add, delete, reorder; each field saves when left and
    shows "Đã lưu";
  - per scene a preview of the frame, or the reason there is none, in red. Pointing at a picture
    (always on a touch screen) shows quick actions over a dark gradient: "Chỉnh khung" for a
    photo or "Cắt video" for a clip, "Vị trí chữ", "Thay" (opens the file chooser) and, for a
    clip, a delete icon ("Xoá video", confirmed). Under the picture one dashed area, "Kéo thả hoặc
    bấm để tải ảnh/video lên", takes a photo (JPG, PNG, WebP, 15 MB) or a clip (MP4, MOV, WebM,
    50 MB) dropped on it or chosen; a photo in place of a clip, or a clip in place of a photo, asks
    first ("Đổi" / "Huỷ"). Then "Chọn từ kho ảnh/video" and "Tìm ảnh" with its source arrow;
  - **"Chỉnh khung"** (photo): a dialog that crops the photo to 9:16 with a "Phóng to" slider
    (1–4×), "Xoay 90°" and "Lật ngang"; dragging moves the photo under the frame. "Áp dụng" cuts
    it in the browser to a JPEG of at most 1080×1920 and stores it in place of the photo, keeping
    where it came from (Pixabay, an AI model…); a crop narrower than 1080 px warns that the photo
    will look soft. Cropping again starts from the cropped photo: picking the photo again is the
    way back. **"Cắt video"** (clip): a muted 9:16 player and a two-handle slider over the clip;
    dragging a handle shows its frame, "Xem thử" plays the chosen part only, and the scene's
    length is the part less the crossfades (0.2 s on each side with a neighbour). A part shorter
    than 1 s or longer than 10 s cannot be applied. "Áp dụng" saves the start and the seconds
    together. A switch plays the clip's sound in the preview only, saying the MP4 never uses it;
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
  - per scene (title included) a "Từ khóa tìm ảnh" field and two Pixabay buttons: "Chọn từ
    Pixabay" opens a dialog with the scene's first keyword already searched (editable, Enter
    searches again) and every result as a thumbnail grid that fits the screen (two columns on a
    phone); clicking one stores it for the scene, closes the dialog and puts the keyword that found
    it first in the scene's keywords. "Tìm ảnh" ("Tìm ảnh khác" once the scene has a photo) takes
    the next result for the saved keywords from the source named on the button (Pixabay until another
    is picked from the arrow menu beside it). The picker's source tab stays as chosen while the page
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
  - the "Thiết lập" tab, every change saved at once: "Âm thanh" (narration on/off, the ElevenLabs
    voice picked from the account's voices with "Nghe thử" playing ElevenLabs' free sample, speed
    Chậm/Vừa/Nhanh, voice level, "Nhỏ nhạc khi có giọng đọc"); the music card (from the library
    ("Chọn từ thư viện", filtered by topic, mood, and name) or an uploaded MP3, optionally saved to
    the library with its topics and mood, with a volume slider); "Hình ảnh" (Chuyển cảnh: Mờ dần,
    Cắt thẳng, Trượt; Chuyển động ảnh: Zoom vào, Zoom ra, Lia ngang, Đứng yên; Độ zoom: Nhẹ, Vừa,
    Mạnh); "Chữ & phụ đề" (a "Chỉnh chữ cho" switch at the top, Các cảnh or Tiêu đề: Tiêu đề shows
    "Tiêu đề giống các cảnh", ticked by default (and unticked, with the yellow box, for a video made
    with the older "Hộp vàng"); unticking starts the title's own look from the scenes' and shows the
    same cards and colour rows for the title only; ticking it again drops the title's look; the
    captions are shown under Các cảnh only, with a note that the title is the thumbnail. For each, the
    Kiểu hộp chữ chosen from small 9:16 previews: Không hộp, then the team's
    own box styles, then a dashed "+ Thêm kiểu" card opening "Thêm kiểu hộp chữ" (Tên kiểu, Màu nền
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
    buttons, and Claude's self-review list;
  - the "Đăng Facebook" card once there is an MP4: the Fanpage (a sole Page is chosen by itself),
    "Đăng ngay" or "Hẹn giờ" (at least 15 minutes
    ahead, within 29 days), "Đăng lên Facebook" with a confirmation, then the scheduled time or a
    "Xem Reel" link. It is disabled while the MP4 is out of date. The pinned comment stays manual;
  - "Nhân bản", "Hủy" for a queued job, "Thử lại" for a failed one, "Xóa".
- **Kho kiến thức** (`/knowledge`): one collapsible line per topic group ("Nhóm chủ đề"), added,
  renamed, and deleted by members; a group with videos cannot be deleted. Opened, it has the script
  prompt, the clone prompt (each with "Khôi phục mặc định"), and the banned words. A new group starts
  empty, and "Tạo video" cannot pick a group without a script prompt. The group is chosen in "Tạo
  video"; a clone keeps its source's group.
- **Thư viện nhạc** (`/music`): the team's tracks with a player, topic and mood tags, source/license
  note ("Chưa ghi nguồn" when empty), who added it and when; filters by topic, mood, and name;
  "Tải nhạc lên" (MP3 up to 20 MB, then name, topics, mood, and source), "Sửa", "Xoá" (videos that
  used the track keep their copy).
- **Affiliate Shopee** (`/affiliate`), two tabs:
  - "Video đã đăng": reels on the Facebook Page, newest first, with the script's suggestions, a
    picker of approved products (labelled with the expected commission per order), and a copy button
    for the pinned comment with one link per product. A product that lost its approval or no longer
    meets the rules stays attached with a yellow tag, and its link is left out of the copied text;
  - "Sản phẩm": products ranked by expected commission per order, with shop, type, rating, sales,
    price, and status; filters by name or shop, topic group, and status; "Thêm sản phẩm", "Sửa",
    "Xoá", "Duyệt", "Bỏ duyệt", "Xuất CSV". A row that fails the rules shows why, in yellow.
- **Đăng bài**, a menu group of two view-only screens. Nothing is posted or approved here: a member
  reviews and posts a video from the "Đăng Facebook" card on its page.
  - **Bài đăng** (`/posts`): videos posted or scheduled, latest time first, with the Fanpage,
    "Đã hẹn lịch" or "Đã đăng", the time in Vietnam time, who posted it, and "Xem Reel" once public.
    The title opens the video.
  - **Lịch đăng bài** (`/calendar`): the same videos in a month view, coloured by status. A video
    opens its page. Everything is in Vietnam time whatever the browser's time zone: the day a video
    sits under, the month it opens on, and the "today" mark.
    On a phone the month is compact, with a dot on each day that has a video, and the chosen day's
    videos are listed under it.
- **Job logs** (`/jobs`): every job with video, kind, status, who started it, start, duration,
  AI call count, the model that wrote a script ("DeepSeek · deepseek-chat"), and error; a row opens
  its video.
- **Cài đặt**, a menu group, last in the sidebar, with two pages: **Cấu hình** and **Kết nối Fanpage**.
  Cấu hình (`/settings`, opening its first tab) is one page titled "Cấu hình" with three tabs, each
  its own address so a link or a reload keeps the tab; the menu keeps "Cấu hình" selected on all three:
  - **Thiết lập mặc định** (`/settings/defaults`, the first tab): the same three cards as
    a video's "Thiết lập" tab plus the music level, saved at once ("Đã lưu mặc định"). They apply
    only to videos created afterwards.
  - **Mô hình AI** (`/settings/ai`): "Đang dùng để viết kịch bản" picks the team's provider (a
    provider not set up yet is greyed out, "chưa cấu hình"). Below, one collapsible line per
    provider with "Đang dùng", "Sẵn sàng" or "Chưa cấu hình" and its model; the one in use is open.
    Opened: "API key" (pasted once with "Lưu key", then shown as "Đã lưu, kết thúc bằng …abcd" with
    "Dán key mới" and "Xoá key"; Claude without a saved key says it uses the server's `.env` key),
    "Base URL" (empty means the default shown as placeholder), "Model" (typed, or picked from the
    names "Kiểm tra kết nối" fetched), then "Lưu", "Kiểm tra kết nối" (enabled once saved) and
    "Dùng để viết kịch bản". What still stops a provider is shown in yellow under its fields.
  - **Nguồn tư liệu** (`/settings/sources`): one card per stock library (Pixabay, Pexels: photos
    and clips; Openverse: photos, no key) with "Sẵn sàng" or "Chưa có key", a switch "Hiện trong
    hộp chọn" that hides a source from the picker and "Tìm ảnh khác" for the whole team, and its API
    key (pasted with "Lưu key", then "Đã lưu, kết thúc bằng …abcd" or "Đang dùng key trong file .env
    của máy chủ", with "Dán key mới", "Xoá key" and a "Lấy key" link); below, one card per AI photo
    provider (Gemini; Cloudflare, whose key is a Workers AI API token) with its model, its key and
    "Đang dùng" on the one `IMAGE_GEN_PROVIDER` picks; last, "Giọng đọc (ElevenLabs)" with the narration key. A
    missing or rejected ElevenLabs key is shown on the voice picker with a link "Mở Nguồn tư liệu".
  - **Kết nối Fanpage** (`/fanpages`, the group's second page, not a tab): a table of Pages with the name and id, the token's last four
    characters, "Đang dùng" or "Ngừng dùng", and who changed it when. "Thêm Fanpage" takes a token,
    "Kiểm tra token" lists the Pages it manages (a sole Page is ticked, one it cannot post to is
    greyed out), and "Lưu" keeps the chosen ones. Each row has "Dán token mới", which must reach
    that Page, and "Ngừng dùng" or "Dùng lại". A stopped Page cannot be posted to.

Phones (below 992 px wide; built):

- The menu collapses into a drawer opened from the header, which shows the logo and the avatar
  only. On a wider screen the sidebar and the header stay in place while the page scrolls.
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
- **First frame = thumbnail:**
  - a close-up food photo filling the frame, with vivid color;
  - the chosen title in a text box centred in the frame, 3–5 lines, with no fade-in.
- **Text box:** a scene whose text is empty has none, so a video can mix scenes with and without
  text, or carry no text at all. An empty title scene leaves the thumbnail without a box, and the
  video is listed under its topic.
  - yellow background (`#FFD60A`) with black text (`#111111`). Outlined text without a box was
    rejected as the default because it is hard to read on bright photos; it is offered only as the
    opt-in "Không hộp" preset below;
  - bold, uppercase, centered, at most 960 px wide;
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
- **Narration:** each scene's on-screen text, then its voice text, read in the ElevenLabs "Adam"
  voice, mixed at full level over the music, starting 0.2 s into the scene. A scene whose narration
  is longer than its seconds is lengthened to fit. The "Giọng đọc" card turns it off for the whole
  video; an empty voice text leaves that scene silent, even when it has on-screen text.
- **Font:** must render Vietnamese diacritics. The default is Be Vietnam Pro Black.
- **Length:** derived from the scene count. A title scene plus 5–7 scenes runs about 30–55 seconds with narration, which lengthens scenes to fit.

### Presets

Each video picks one of each ([reels_render/options.py](../worker/src/reels_render/options.py));
free colour or size sliders are not offered. A person watches a sample of each before they are
relied on (samples in the PR that added them).

- **Transition:** Mờ dần (the 0.4 s crossfade above), Cắt thẳng (hard cut; each scene is exactly its
  seconds), Trượt (the next scene slides in from the right over 0.4 s). The total length is the
  same for all three.
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
  the speed (ElevenLabs `speed` 0.9 / 1.0 / 1.1), the level (0–100%), and "Nhỏ nhạc khi có giọng
  đọc", which compresses the music under the narration (a sidechain, about a quarter of its level).
  Changing the voice or speed makes the narration again on the next render.
- **Captions (phụ đề theo giọng đọc):** content scenes with narration only, never the title scene.
  White bold 58 px text on a rounded black box at 67%, at most two lines and four words, centred
  just above the scene's text box (or with its bottom at y = 1440 when the scene has none).
  "Từng cụm" shows each phrase while it is read; "Từng từ" also lights the word being read in
  yellow. Phrases break after punctuation. The timing is an estimate spread over the narration by
  letters, not ElevenLabs' timestamps, so it can run slightly ahead or behind.

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
