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
