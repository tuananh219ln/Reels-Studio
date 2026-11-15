# Routine for an always-on assistant (Muse) to fill footage

Use this when the team's automatic footage switch (Cài đặt › Nguồn tư liệu) is off, to avoid the image-capable
LLM's API cost: the assistant on the member's own Claude plan looks at the frames instead. It needs the Reels
Studio MCP connection with edit permission ([chatgpt.md](chatgpt.md)). Paste the text below into the assistant as
a standing instruction (or schedule it, if the assistant can run on a timer; otherwise send it by message, e.g.
"bổ sung tư liệu cho video mới").

```text
Nhiệm vụ: bổ sung ảnh/clip cho các cảnh còn thiếu trong video của tôi trên Reels Studio. Không render, không đăng.

1. Gọi "Liệt kê cảnh thiếu tư liệu". Không có cảnh nào thì báo "không có việc" và dừng.
2. Với mỗi cảnh (xử lý tối đa 15 cảnh mỗi lượt):
   a. Gọi "Tìm clip cho cảnh" với từ khóa đầu tiên của cảnh (tiếng Việt cho youtube; tiếng Anh cho pexels, pixabay).
      Thử youtube, rồi pexels, rồi pixabay. Nếu chưa ra thì thử từ khóa thứ hai của cảnh.
   b. Xem các ảnh đoạn 0–5. Chọn đoạn minh họa ĐÚNG đối tượng và hành động của cảnh, quay thật, rõ nét, không
      watermark, không chữ lớn che hình, không chỉ có người nói trước camera. Không có đoạn đúng thì từ chối, đừng
      chọn đại.
   c. Gọi "Dùng clip đã chọn cho cảnh" với mã ứng viên và số đoạn. Gọi "Xem khung hình của cảnh" để kiểm tra.
   d. Không có clip hợp sau 3 lần tìm: gọi "Tìm ảnh kho miễn phí", chọn ảnh đúng món rồi "Dùng ảnh kho cho cảnh".
3. Gặp lỗi tải hoặc CAPTCHA thì bỏ qua cảnh đó, không vượt chặn, không tìm bằng cách khác.
4. Cuối lượt nhắn cho tôi: video nào, cảnh nào đã có clip/ảnh (kèm link nguồn), cảnh nào chưa tìm được và vì sao.
   Ảnh Wikimedia cần ghi nguồn thì nêu dòng credit. Tôi xem lại rồi bấm render.
```

Notes: clips and photos are other people's, so the member is responsible for rights (the same as pasting a link);
scenes the assistant fills keep their source link and the "check again" mark. YouTube may refuse downloads from the
server; the assistant then falls back to Pexels, Pixabay and photos.

## The clip flow with TikTok (owner, 2026-11-15)

Run by message ("lấy clip TikTok cho video 170") or inside a building job, by an assistant that has a browser. The
common part, then the page's own appendix.

```text
LUỒNG GẮN CLIP (chung mọi nhóm)
1. Đọc video ("Đọc video"): no_people cho biết nhóm có bật "Không dùng cảnh có người".
2. Tìm link TikTok bằng trình duyệt: https://www.tiktok.com/search/video?q=<từ khóa>, lấy khoảng 8 link /video/.
   CAPTCHA thì dừng phần TikTok và báo, không vượt chặn.
3. "Thêm vào kho từ link" (urls, tối đa 10 mỗi lần); link lỗi thì bỏ.
4. "Xem nhiều khung hình của clip" (media_id, start, seconds = thời lượng cảnh): soát CẢ ĐOẠN, chọn đoạn đúng đối
   tượng và hành động, không chữ to của tác giả; no_people=true thì không có mặt hay thân người (bàn tay thì được).
5. "Gắn clip cho cảnh" (scene_id, media_id, video_start, blur = vùng @tên kênh hay chữ dính): app giữ thời lượng
   cảnh, dời chữ của cảnh lên chỗ mờ và tự thêm sticker che phần còn lộ; xem ảnh trả về.
6. Render khi đã được phép; xem khung MP4 ở giữa mỗi cảnh. Còn lỗi thì sửa rồi render lại.

PHỤ LỤC ĂN LÀNH: mỗi cảnh nội dung và cảnh tiêu đề một clip đúng món (ngày slides; ngày single giữ ảnh tĩnh);
no_people bật: không người; từ khóa = keywords[0] tiếng Việt của cảnh.

PHỤ LỤC THREADS: chỉ clip nền ở cảnh tiêu đề, theo vibe (V1 lưới tối, V2 ấm cúng, V3 minecraft parkour không chữ,
V4 mukbang; V5, V6 dùng ảnh tĩnh); không áp luật người; cảnh không chữ nên không dời chữ, không sticker; sau
"Sửa nội dung đăng" đọc lại caption và hashtag bằng "Đọc video".

KHUÔN 3AM (Threads, khi kịch bản là đọc thẻ):
- Mỗi thẻ một cảnh, cảnh không chữ. "Gắn thẻ cho cảnh" (ảnh thẻ trắng trong Kho hoặc link ảnh, top 220, width 90).
- Nền: mỗi cảnh một clip nền ("Gắn clip cho cảnh"), chuyển cảnh "cut", tắt tiếng gốc; clip ngắn hơn cảnh thì bật
  "Lặp clip". Muốn nền đổi theo thẻ thì cảnh sau dùng clip khác.
- Thẻ dày (ảnh lồng, nhiều reply, list dài): "Hiện dần thẻ" với cut_y ở cuối mỗi phần (xem kích thước ảnh trong câu
  trả lời của "Gắn thẻ cho cảnh") và lời đọc của từng phần. Thẻ một câu ngắn thì để hiện nguyên.
- Đoạn kết tách riêng (chữ phủ, meme) có thể đọc bằng giọng khác: "Sửa cảnh" với voice_id của cảnh đó.
- Tốc độ đọc nhanh kiểu 3AM: "Tùy chọn của video" voice_speed 1.4–1.5.
- Xem lại bằng "Xem khung hình của cảnh" (thẻ hiện nguyên), sau render xem khung MP4 ở đầu và cuối cảnh hiện dần.
```
