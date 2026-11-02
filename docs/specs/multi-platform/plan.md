# Kế hoạch: Đăng đa nền tảng không flop (Facebook + TikTok + YouTube Shorts)

> Trạng thái: kế hoạch chiến lược, viết 2026-11-02. Chưa phải brief thi công — các mục tool ở cuối sẽ tách thành brief riêng khi tới lượt.
> Tiền đề đã chốt (xem MEMORY.md): tool dùng chung, tiền nhận riêng — mỗi thành viên có Page Facebook, tài khoản TikTok, tài khoản Shopee riêng; đơn vị sở hữu tiền là từng lượt đăng (video × nền tảng × tài khoản).
> Chính sách nền tảng đổi nhanh: các ngưỡng và quy tắc dưới đây kiểm chứng qua nguồn công khai ngày 2026-11-02 (xem cuối file); trước khi đăng hàng loạt trên một nền tảng mới, kiểm tra lại trang chính sách của nền tảng đó.

## Luận điểm cốt lõi: 1 ý tưởng → N bản native, KHÔNG BAO GIỜ đăng cùng 1 file

Flop đa nền tảng thường không đến từ nội dung dở, mà từ 4 lỗi sau — kế hoạch này được xây để tránh đúng 4 lỗi đó:

1. **Đăng cùng một file lên nhiều nơi.** File giống nhau = dấu vết trùng lặp cho hệ thống phát hiện nội dung trùng; chưa kể watermark của nền tảng này dính sang nền tảng kia (tải video từ TikTok rồi đăng lên Facebook là cách flop chắc chắn nhất: vừa dính watermark vừa bị bóp phân phối). Quy tắc sắt: mỗi nền tảng nhận một bản render riêng từ tool, không tải chéo video đã đăng.
2. **Hai người đăng cùng một video lên Facebook.** Meta nói rõ: video của chính mình được đăng lên nhiều Page của mình, nhưng bản sao sẽ bị giảm phân phối để bản gốc được xem; Page lặp lại nội dung không nguyên bản sẽ bị mất đề xuất và mất kiếm tiền (thường 90 ngày). Hai thành viên có Page riêng thì KHÔNG được đăng cùng một video — mỗi người cần một biến thể thật (xem "Biến thể theo nền tảng" bên dưới), kể cả khi cùng một ý tưởng và cùng link aff của riêng mình.
3. **Dùng một kiểu link aff cho mọi nền tảng.** Shopee chỉ kiếm tiền trên Facebook (link trong bình luận ghim) và YouTube (link trong mô tả). Trên TikTok, link Shopee ngoài không tạo hoa hồng TikTok Shop — tiền aff TikTok đi qua giỏ hàng TikTok Shop gắn trong video, tức mỗi người cần tài khoản TikTok Shop affiliate riêng, không phải cứ dán link Shopee là xong.
4. **Dùng một kiểu claim sức khỏe, một kiểu nhãn AI cho mọi nền tảng.** Mỗi nền tảng có luật riêng về claim y tế và nội dung AI — vi phạm ở một nơi không chỉ flop video đó mà có thể phạt cả tài khoản.

## Ma trận khác biệt theo nền tảng

| Khía cạnh | Facebook Reels | TikTok | YouTube Shorts |
|---|---|---|
| Tiền view | Kiếm tiền Reels theo Page (Page phải đủ điều kiện, không vi phạm nguyên bản) | Creator Rewards yêu cầu video dài từ 1 phút trở lên — video 30–45s hiện tại KHÔNG đủ điều kiện nhận tiền view TikTok | YPP: 1.000 sub + 10 triệu lượt xem Shorts hợp lệ/90 ngày, hoặc 4.000 giờ xem video dài/12 tháng (xem deadline 2027 bên dưới) |
| Tiền aff | Shopee: link trong bình luận ghim (app hiện chưa tự đăng/ghim — thành viên dán tay) | TikTok Shop: giỏ hàng gắn trong video, tài khoản Shop affiliate riêng từng người; link Shopee ngoài không tạo hoa hồng | Shopee: link trong mô tả + bình luận ghim, kèm công khai quảng cáo |
| Nội dung trùng / reused | Mạnh nhất: nội dung không nguyên bản → giảm phân phối từng video; Page lặp lại → không được đề xuất + mất kiếm tiền ~90 ngày. "Nâng cấp có ý nghĩa" theo Meta 2026 là người thật trên màn hình trình bày thông tin mới — viền, watermark, caption, nhạc, đổi tốc độ, khâu clip KHÔNG tính | Nội dung gốc là điều kiện của chương trình thưởng; đăng lại nội dung người khác hoặc trùng lặp hàng loạt bị giảm phân phối | YPP từ chối/đình chỉ kênh có phần lớn nội dung reused (dùng lại clip/ảnh mà không thêm giá trị bình luận, giáo dục đáng kể) |
| Nhãn AI | Meta có thể tự dán nhãn "AI info" khi phát hiện C2PA/SynthID với video/âm thanh chân thực; ảnh không bắt buộc nhãn | BẮT BUỘC tự gắn nhãn nội dung AI chân thực (dùng công tắc AIGC lúc đăng); nội dung không gắn nhãn có thể bị gỡ/gắn strike dù hệ thống tự phát hiện. Viết kịch bản/caption/hashtag bằng AI thì KHÔNG cần nhãn — nhãn áp cho hình/tiếng chân thực | BẮT BUỘC khai báo nội dung bị chỉnh sửa/tổng hợp chân thực (ô "Altered or synthetic content" lúc đăng) |
| Claim sức khỏe | Meta phạt cả câu đúng sự thật nếu diễn đạt y tế giật gân — dùng "hỗ trợ", "tốt cho", tránh "khắc tinh", "chữa khỏi" | Cấm thông tin y tế gây hiểu lầm; claim chữa bệnh là vùng nguy hiểm nhất | Cấm thông tin sai lệch y tế trái với hướng dẫn của cơ quan y tế; claim chữa bệnh là vùng nguy hiểm nhất |
| Nhạc | Nhạc trong thư viện nền tảng hoặc nhạc có bản quyền dùng được cho Reels | Tài khoản doanh nghiệp bị hạn chế nhạc thương mại — dùng Commercial Music Library hoặc nhạc miễn phí bản quyền; nhạc trending của tài khoản cá nhân KHÔNG mang sang tài khoản doanh nghiệp/Page khác được | Nhạc Shorts dùng thư viện của YouTube; nhạc ngoài mang vào phải có quyền |
| Định dạng | 9:16, 30–45s hiện tại là vừa | 9:16; cân nhắc bản 60s+ riêng cho Creator Rewards (xem Giai đoạn 1) | 9:16, tối đa 3 phút; giữ 30–60s cho nhịp kênh hiện tại |
| Khung giờ tham khảo | 11–12h hoặc 19–21h (dữ liệu kênh hiện tại) | Buổi tối 19–23h (khán giả VN lướt mạnh nhất) | Chiều/tối; Shorts sống bằng feed đề xuất nhiều hơn khung giờ cố định |

## Biến thể theo nền tảng: từ 1 kịch bản ra 3 bản native

Không làm lại kịch bản từ đầu cho từng nền tảng. Một ý tưởng đi qua cùng một kịch bản gốc, rồi biến thể ở những điểm rẻ mà hệ thống mỗi nền tảng nhìn vào:

- **Hook 3 giây đầu khác nhau.** Facebook: mốc tuổi + lợi ích ("Sau 50 tuổi đừng thiếu 5 món này"). TikTok: câu hỏi khơi bình luận ("Nhà bạn có ai mất ngủ kiểu này không?"). YouTube: tiêu đề chứa từ khóa tìm kiếm ("Ăn gì tốt cho xương khớp sau 50 tuổi").
- **Thứ tự/cách chọn ảnh khác nhau** giữa các biến thể (đổi 1–2 ảnh, đổi cảnh mở đầu) — đủ để không còn là cùng một file, và cũng là biến thể hợp lệ cho luật "một góc thay đổi" của brief performance-loop.
- **Lời đọc PHẢI thêm thông tin, không chỉ đọc chữ trên màn hình.** Hợp đồng kịch bản hiện tại đã yêu cầu vậy (lời đọc nói tiếp ý, thêm cách ăn/mẹo nhỏ) — giữ kỷ luật này vì Meta 2026 coi "đọc lại những gì đã hiện trên màn hình mà không thêm gì có ý nghĩa" là nội dung không nguyên bản.
- **Caption + hashtag viết riêng từng nền tảng** (không copy-paste): Facebook 3–5 hashtag + câu hỏi cuối; TikTok caption ngắn, hashtag ít, câu hỏi khơi bình luận; YouTube mô tả chứa từ khóa + link aff + công khai quảng cáo.
- **Nhạc riêng từng nền tảng** theo hàng nhạc của ma trận trên; không mang nhạc trending TikTok sang Facebook/YouTube.
- **Mỗi nền tảng một lịch đăng riêng, so le nhau** (không đăng cùng một phút lên cả ba) — vừa để mỗi nền tảng coi nội dung là native, vừa để đọc số liệu sớm của bản đầu trước khi đăng bản sau.
- **Tài khoản mới phải warm-up:** tuần đầu 1 video/ngày, không đăng ồ ạt 3 video/ngày ngay; tăng dần khi tài khoản đã có lịch sử đăng đều và không vi phạm.

## An toàn sức khỏe và AI: checklist bắt buộc trước mỗi lần đăng

Áp cho MỌI nền tảng, không chỉ Facebook (đây là lý do mục disclaimer trong backlog cần được ưu tiên lên, không để "deferred" nữa):

- [ ] Không câu nào hứa chữa bệnh, thay thuốc, diệt tế bào, đặc trị — kể cả trong tiêu đề, chữ cảnh, lời đọc, caption, bình luận ghim.
- [ ] Không số liệu, tỉ lệ, tên nghiên cứu/bác sĩ tự bịa — chỉ lợi ích phổ thông đã biết rộng rãi (cho tới khi food bank duyệt xong).
- [ ] Có câu miễn trừ "Tham khảo, không thay thế tư vấn bác sĩ" trong caption/mô tả (và cân nhắc khung cuối video trên YouTube/TikTok).
- [ ] Ảnh AI chân thực: TikTok bật công tắc AIGC; YouTube tick ô synthetic content; Facebook để Meta tự dán nhãn, không cố giấu.
- [ ] Không watermark nền tảng khác, không logo ứng dụng khác trong khung hình.
- [ ] Link aff đúng người, đúng nền tảng: Facebook/YouTube = link Shopee của người đăng; TikTok = giỏ TikTok Shop của người đăng. Kiểm tra lại trước khi bấm đăng — đây là bước khóa tiền, không làm qua loa.
- [ ] Sản phẩm aff là sản phẩm đã duyệt trong tool (đạt tiêu chí shop/sao/lượt bán); TPCN thì thêm câu "không phải là thuốc" khi đăng (mục backlog đã có).

## Đo lường: thắng ở nền tảng nào thì nhân ở nền tảng đó

- Số liệu đo theo từng lượt đăng (video × nền tảng × tài khoản), KHÔNG gộp median hai Page hay hai nền tảng lại với nhau — khán giả và thuật toán khác nhau nên "thắng" phải tính riêng từng nơi (brief performance-loop đã thiết kế publication_metrics theo từng publication; khi mở rộng nền tảng, giữ nguyên nguyên tắc này).
- Một video thắng trên Facebook không tự động thắng trên TikTok: chỉ nhân bản biến thể cho đúng nền tảng nó thắng.
- Theo dõi thêm chỉ số sức khỏe tài khoản, không chỉ view: trạng thái kiếm tiền của Page (Meta Business Suite), Account Status TikTok, trạng thái YPP YouTube — vi phạm chính sách giết tài khoản nhanh hơn flop một video.

## Lộ trình

- **Giai đoạn 0 — Củng cố Facebook (hiện tại, trước khi mở thêm nền tảng).** Kỷ luật biến thể giữa các thành viên (không đăng cùng video lên 2 Page); đưa disclaimer vào caption; làm tính năng tự đăng + ghim bình luận để khóa link đúng người; đo 48h theo từng publication.
- **Giai đoạn 1 — TikTok (làm tay trước, tự động sau).** Mỗi người lập tài khoản TikTok + TikTok Shop affiliate riêng; đăng tay qua app TikTok (bật nhãn AIGC, gắn giỏ Shop); thử bản 60s+ để đủ điều kiện Creator Rewards; đọc số liệu 2–4 tuần rồi mới tính tới tích hợp đăng tự động (API đăng TikTok cần phê duyệt ứng dụng, không phải bật là có).
- **Giai đoạn 2 — YouTube Shorts (có deadline thật).** Mỗi người lập kênh riêng. Ngưỡng YPP hiện tại là 1.000 sub + 10 triệu lượt xem Shorts/90 ngày; **từ 01/02/2027, người mới đăng ký cần 8.000 giờ xem hoặc 20 triệu lượt xem Shorts/90 ngày, và muốn giữ tiền Shorts thì mỗi tháng phải duy trì trên 10 triệu lượt xem/90 ngày** — nghĩa là càng vào YPP sớm càng rẻ. Mở kênh và đăng đều ngay cả khi chưa đủ ngưỡng, đừng đợi đủ rồi mới bắt đầu.
- **Giai đoạn 3 — Tự động hóa trong tool.** Mở rộng publications sang tiktok/youtube (hiện chỉ có facebook); mỗi tài khoản nền tảng gắn với đúng một thành viên (owner) và chỉ người đó (hoặc người được ủy quyền tường minh) mới đăng lên nó; caption/hashtag/mô tả/link aff theo từng nền tảng trong cùng một video; cờ nhãn AI theo từng nền tảng; disclaimer tự chèn vào caption/mô tả.

## Rủi ro flop và đối sách (tóm tắt)

- Đăng cùng file / cùng video cho 2 người → biến thể thật mỗi người, mỗi nền tảng.
- Claim y tế giật gân → ngôn ngữ "hỗ trợ/tốt cho" + disclaimer + từ cấm theo topic.
- Quên nhãn AI → checklist đăng + cờ nhãn AI trong tool ở Giai đoạn 3.
- Link aff nhầm người/nhầm nền tảng → kiểm tra bước đăng + đối soát theo từng lượt đăng.
- Nhạc sai bản quyền → nhạc theo thư viện từng nền tảng, không mang nhạc trending chéo nền tảng.
- Tài khoản mới đăng ồ ạt → warm-up 1 video/ngày rồi tăng dần.
- Dồn hết vào tiền view → mỗi nền tảng có đường tiền khác nhau (FB: view + Shopee; TikTok: Shop là chính, view chỉ khi video 60s+; YouTube: view sau khi đủ YPP, aff ngay từ đầu) — đừng đánh giá TikTok bằng thước view của Facebook.

## Nguồn kiểm chứng ngày 2026-11-02

- YouTube Partner Program (ngưỡng 1.000 sub + 10M Shorts views/90 ngày; thay đổi từ 01/02/2027): https://www.shopify.com/blog/youtube-shorts-monetization , https://air.io/en/monetization/youtube-partner-program-requirements-2026-the-complete-guide
- TikTok bắt buộc gắn nhãn nội dung AI chân thực, nội dung gắn nhãn đúng không bị giảm phân phối: https://oakgen.ai/blog/do-you-have-to-label-ai-videos , https://kabo.sh/guides/tiktok-ai-content-label
- Meta siết nội dung không nguyên bản (07/2025, cập nhật 03/2026): bản sao giảm phân phối, Page lặp lại mất đề xuất + mất kiếm tiền ~90 ngày: https://www.clyper.io/guides/facebook-unoriginal-content-policy , https://contentmonetizing.com/en/how-facebook-detects-unoriginal-content/
