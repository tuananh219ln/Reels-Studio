"use client";

import { Card, Flex, Typography } from "antd";
import Link from "next/link";
import Logo from "@/components/Logo";

/** Each section of the terms. Like the privacy policy, it describes what the app really does: keep it in step with
 * docs/ when that changes (who may sign in, what is posted where, the services a feature calls). */
const SECTIONS: { heading: string; body: string[] }[] = [
  {
    heading: "Phạm vi",
    body: [
      "Reels Studio là công cụ nội bộ của một nhóm nhỏ (khoảng 5 người), dùng để làm video dọc 9:16 và đăng lên các Trang Facebook của nhóm. Điều khoản này áp dụng cho mọi người dùng công cụ và cho các Trang được kết nối với công cụ.",
    ],
  },
  {
    heading: "Tài khoản",
    body: [
      "Công cụ không mở đăng ký: tài khoản do thành viên của nhóm tạo cho người được nhóm cho phép.",
      "Mỗi người tự giữ mật khẩu của mình và không cho người khác dùng chung tài khoản. Tài khoản có thể bị khoá khi người dùng rời nhóm hoặc vi phạm điều khoản này.",
    ],
  },
  {
    heading: "Sử dụng được phép",
    body: [
      "Chỉ dùng công cụ để làm và đăng nội dung cho các Trang mà nhóm có quyền quản lý.",
      "Nội dung đăng lên phải tuân theo Tiêu chuẩn cộng đồng và Chính sách nội dung có thương hiệu của Meta, cùng các quy định của TikTok, Shopee khi dùng các nền tảng này.",
      "Không đăng nội dung sai sự thật, phóng đại công dụng sức khoẻ, vi phạm bản quyền hoặc xúc phạm người khác. Công cụ cảnh báo các từ bị cấm, nhưng người đăng vẫn chịu trách nhiệm về nội dung cuối cùng.",
    ],
  },
  {
    heading: "Nội dung và bản quyền",
    body: [
      "Ảnh, clip, nhạc và lời đọc trong video do thành viên tải lên hoặc tạo bằng các dịch vụ bên thứ ba. Người tải lên đảm bảo mình có quyền sử dụng chúng.",
      "Kịch bản và ảnh do AI tạo ra cần được thành viên đọc lại và chỉnh sửa trước khi đăng.",
    ],
  },
  {
    heading: "Dịch vụ bên thứ ba",
    body: [
      "Công cụ gọi tới các dịch vụ như Meta (Facebook), các nhà cung cấp AI, ElevenLabs, các kho ảnh, TikTok và Shopee. Việc dùng các dịch vụ này còn tuân theo điều khoản riêng của từng dịch vụ. Dữ liệu được gửi cho ai được nêu trong Chính sách quyền riêng tư.",
    ],
  },
  {
    heading: "Người xem và người bình luận",
    body: [
      "Người xem video trên Facebook không cần tài khoản trên công cụ này. Thành viên có thể trả lời hoặc ẩn bình luận dưới các reel do công cụ đăng; bình luận được xử lý như mô tả trong Chính sách quyền riêng tư.",
    ],
  },
  {
    heading: "Giới hạn trách nhiệm",
    body: [
      "Công cụ được cung cấp nguyên trạng để nhóm dùng nội bộ. Chúng tôi cố gắng để công cụ chạy ổn định, nhưng không bảo đảm công cụ luôn sẵn sàng, không lỗi, hay video luôn được các nền tảng chấp nhận và phân phối.",
    ],
  },
  {
    heading: "Liên hệ",
    body: ["Mọi câu hỏi về điều khoản này, vui lòng nhắn tin cho Trang Facebook đã đăng video."],
  },
  {
    heading: "Thay đổi điều khoản",
    body: ["Khi điều khoản thay đổi, ngày cập nhật ở đầu trang sẽ được đổi theo."],
  },
];

/** The public terms of service (/terms), the URL a Meta app can list beside its privacy policy. A client component:
 * antd's Typography is one, and a server page cannot reach its Title and Paragraph. */
export default function TermsOfService() {
  return (
    <Flex justify="center" style={{ minHeight: "100vh", padding: "48px 16px", boxSizing: "border-box" }}>
      <Flex vertical gap={16} style={{ width: "100%", maxWidth: 720 }}>
        <Flex justify="center">
          <Logo size={20} />
        </Flex>
        <Card>
          <Typography.Title level={1} style={{ marginTop: 0, fontSize: 28 }}>
            Điều khoản sử dụng
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
          <Typography.Paragraph>
            Xem thêm <Link href="/privacy">Chính sách quyền riêng tư</Link>.
          </Typography.Paragraph>
        </Card>
      </Flex>
    </Flex>
  );
}
