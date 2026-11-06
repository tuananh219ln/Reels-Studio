"use client";

import { Card, Flex, Typography } from "antd";
import Logo from "@/components/Logo";

/** Each section of the policy. It says what the app really keeps and sends: keep it in step with docs/ when that
 * changes (comments, tokens, the services a feature calls). */
const SECTIONS: { heading: string; body: string[] }[] = [
  {
    heading: "Reels Studio là gì",
    body: [
      "Reels Studio là công cụ nội bộ của một nhóm nhỏ (khoảng 5 người), dùng để làm video dọc 9:16 và đăng lên các Trang Facebook của nhóm. Công cụ không mở đăng ký: tài khoản do quản trị viên của nhóm tạo.",
    ],
  },
  {
    heading: "Dữ liệu chúng tôi lưu",
    body: [
      "Tài khoản thành viên: email, tên và mật khẩu (chỉ lưu dạng băm).",
      "Mã truy cập (token) Trang Facebook, lưu đã mã hoá: dùng để đăng reel, đọc số liệu của Trang và bài đăng, đọc, trả lời và ẩn bình luận.",
      "Mã API của các dịch vụ AI và kho ảnh do thành viên dán vào, lưu đã mã hoá và không bao giờ hiện lại.",
      "Nội dung video: kịch bản, cảnh, ảnh, clip, nhạc và giọng đọc.",
      "Số liệu của Trang và bài đăng do Meta cung cấp: lượt xem, tiếp cận, chia sẻ, bình luận, cảm xúc, thời gian xem. Đây là số tổng hợp, không gắn với từng người xem.",
      "Bình luận dưới các reel do công cụ đăng: tên người bình luận và nội dung bình luận, để thành viên trả lời hoặc ẩn.",
      "Sản phẩm, link tiếp thị liên kết (Shopee, TikTok) và doanh thu mà thành viên nhập.",
    ],
  },
  {
    heading: "Dữ liệu được dùng để làm gì",
    body: [
      "Chỉ để vận hành công cụ: làm và đăng video, xem hiệu quả bài đăng, quản lý link tiếp thị liên kết và trả lời bình luận. Chúng tôi không dùng dữ liệu để quảng cáo và không bán dữ liệu cho ai.",
    ],
  },
  {
    heading: "Dữ liệu được gửi cho ai",
    body: [
      "Mỗi tính năng chỉ gửi phần dữ liệu nó cần cho dịch vụ thực hiện nó:",
      "Meta (Facebook Graph API): video, mô tả bài, trả lời bình luận; đọc số liệu và bình luận.",
      "Nhà cung cấp AI do nhóm chọn để viết kịch bản (như Anthropic Claude, OpenAI, Google Gemini, Groq, DeepSeek, OpenRouter) và để tạo ảnh (như Cloudflare Workers AI): chủ đề, kịch bản và mô tả cảnh.",
      "ElevenLabs: lời đọc của video, để tạo giọng đọc.",
      "Pexels, Pixabay, Openverse: từ khoá tìm ảnh. TikTok: chỉ khi thành viên dán link clip để tải.",
      "Shopee: để lấy link tiếp thị liên kết và báo cáo.",
      "ChatGPT: chỉ khi một thành viên tự kết nối tài khoản của mình, để soạn bản nháp video.",
      "Cloudflare chạy phần giao diện web. Dữ liệu và file video được lưu trên máy chủ riêng của nhóm.",
    ],
  },
  {
    heading: "Người xem video",
    body: [
      "Người xem không có tài khoản trên công cụ này. Với bình luận, công cụ chỉ lưu tên và nội dung mà Facebook cho Trang đọc, và không dùng chúng vào việc gì khác ngoài trả lời hoặc ẩn bình luận.",
    ],
  },
  {
    heading: "Lưu trữ và xoá dữ liệu",
    body: [
      "Token của Trang ngừng được dùng khi Trang bị ngừng dùng trong công cụ, và bị xoá cùng Trang khi Trang được gỡ khỏi công cụ.",
      "Tài khoản thành viên không bị xoá mà bị khoá, để giữ lịch sử ai đã đăng bài nào. Thành viên có thể yêu cầu quản trị viên khoá tài khoản của mình.",
      "Người bình luận có thể tự xoá bình luận trên Facebook, hoặc nhắn tin cho Trang để yêu cầu xoá bản đã lưu trong công cụ.",
    ],
  },
  {
    heading: "Liên hệ",
    body: [
      "Mọi câu hỏi về chính sách này, hoặc yêu cầu xem và xoá dữ liệu, vui lòng nhắn tin cho Trang Facebook đã đăng video.",
    ],
  },
  {
    heading: "Thay đổi chính sách",
    body: ["Khi chính sách thay đổi, ngày cập nhật ở đầu trang sẽ được đổi theo."],
  },
];

/** The public privacy policy (/privacy), the URL a Meta app needs to go Live. A client component: antd's Typography
 * is one, and a server page cannot reach its Title and Paragraph. */
export default function PrivacyPolicy() {
  return (
    <Flex justify="center" style={{ minHeight: "100vh", padding: "48px 16px", boxSizing: "border-box" }}>
      <Flex vertical gap={16} style={{ width: "100%", maxWidth: 720 }}>
        <Flex justify="center">
          <Logo size={20} />
        </Flex>
        <Card>
          <Typography.Title level={1} style={{ marginTop: 0, fontSize: 28 }}>
            Chính sách quyền riêng tư
          </Typography.Title>
          <Typography.Paragraph type="secondary">
            Reels Studio, công cụ nội bộ làm video dọc 9:16. Cập nhật lần cuối: 06/11/2026.
          </Typography.Paragraph>
          {SECTIONS.map((section) => (
            <section key={section.heading}>
              <Typography.Title level={2} style={{ fontSize: 20 }}>
                {section.heading}
              </Typography.Title>
              {section.body.map((paragraph) => (
                <Typography.Paragraph key={paragraph}>{paragraph}</Typography.Paragraph>
              ))}
            </section>
          ))}
        </Card>
      </Flex>
    </Flex>
  );
}
