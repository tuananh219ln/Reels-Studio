import { formatDateTime, type VideoDetail } from "@/lib/api";
import { Typography } from "antd";

type Line = { key: string; platform: string; state: string; where: string; url: string | null };

const TIKTOK_STATE = { pending: "đang gửi lên", published: "đã lên", cancelled: "" } as const;

/** The posts of the video still on a platform (or on their way there, or waiting for their time): what a member needs
 * to see before deleting the video, as deleting it removes them from the app only, never from the platform. */
export function postLines(video: Pick<VideoDetail, "publications" | "tiktok_posts" | "manual_posts">): Line[] {
  const lines: Line[] = [];
  for (const post of video.publications) {
    if (post.status === "cancelled" || post.status === "deleted") continue;
    const state =
      post.status === "published"
        ? `đã đăng lúc ${formatDateTime(post.at)}`
        : post.status === "scheduled" && post.scheduled_at
          ? `hẹn đăng lúc ${formatDateTime(post.scheduled_at)}`
          : "đang đăng";
    lines.push({
      key: `fb-${post.id}`,
      platform: "Facebook",
      state,
      where: [post.fanpage, post.created_by].filter(Boolean).join(", "),
      url: post.url,
    });
  }
  for (const post of video.tiktok_posts) {
    if (post.status === "cancelled") continue;
    lines.push({
      key: `tt-${post.id}`,
      platform: "TikTok",
      state: `${TIKTOK_STATE[post.status]} ${formatDateTime(post.at)}${post.mode === "draft" ? " (nháp trong hộp thư)" : ""}`,
      where: [post.account, post.created_by].filter(Boolean).join(", "),
      url: post.url,
    });
  }
  for (const post of video.manual_posts) {
    if (post.status === "deleted") continue;
    const state =
      post.status === "pending"
        ? "đang đăng"
        : post.status === "scheduled" && post.scheduled_at
          ? `hẹn đăng lúc ${formatDateTime(post.scheduled_at)}`
          : post.status === "private"
            ? "đã tải lên riêng tư"
            : `đã đăng lúc ${formatDateTime(post.at)}`;
    lines.push({
      key: `${post.platform}-${post.id}`,
      platform: post.platform_label,
      state,
      where: [post.channel, post.fanpage, post.created_by].filter(Boolean).join(", "),
      url: post.url,
    });
  }
  return lines;
}

/** Why "Xóa video" is greyed out for this video, or null: it is posted somewhere (kept for the view report, as the api's
 * bulk delete does) or a job holds it. */
export function deleteBlock(
  video: Pick<VideoDetail, "publications" | "tiktok_posts" | "manual_posts" | "locked">,
): string | null {
  const posted =
    video.publications.some((post) => post.status === "published") ||
    video.tiktok_posts.some((post) => post.status === "published") ||
    video.manual_posts.some((post) => post.status === "published");
  if (posted) return "Video đã đăng, cần giữ để làm báo cáo view";
  if (video.locked) return "Video đang render";
  return null;
}

/** The body of the "Xóa video" confirmation: what is deleted, and every post the video has on a platform. */
export default function DeleteVideoContent({ video }: { video: VideoDetail | null }) {
  const lines = video ? postLines(video) : [];
  return (
    <div data-testid="delete-video-content">
      <Typography.Paragraph>
        Xóa hẳn video, các cảnh, job và mọi file (ảnh, MP4, ảnh thu nhỏ). Không khôi phục được.
      </Typography.Paragraph>
      {lines.length === 0 ? (
        <Typography.Paragraph type="secondary">
          Video chưa có bài nào trên Facebook, Instagram, TikTok hay YouTube.
        </Typography.Paragraph>
      ) : (
        <>
          <Typography.Paragraph strong style={{ marginBottom: 4 }}>
            Video đang có {lines.length} bài trên nền tảng:
          </Typography.Paragraph>
          <ul data-testid="delete-video-posts" style={{ margin: "0 0 8px", paddingLeft: 20 }}>
            {lines.map((line) => (
              <li key={line.key}>
                <strong>{line.platform}</strong>: {line.state}
                {line.where && ` · ${line.where}`}
                {line.url && (
                  <>
                    {" · "}
                    <a href={line.url} target="_blank" rel="noreferrer">
                      Xem bài
                    </a>
                  </>
                )}
              </li>
            ))}
          </ul>
          <Typography.Paragraph type="warning">
            Các bài này vẫn còn trên nền tảng sau khi xóa video, nhưng app sẽ không còn theo dõi, đo view hay quản lý
            chúng nữa. Muốn gỡ bài Facebook khỏi Page, hãy bấm “Xóa” ở từng bài trước khi xóa video.
          </Typography.Paragraph>
        </>
      )}
    </div>
  );
}
