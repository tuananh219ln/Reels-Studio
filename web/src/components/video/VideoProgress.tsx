"use client";

import {
  CheckCircleFilled,
  ClockCircleOutlined,
  ExclamationCircleFilled,
  LoadingOutlined,
  RightOutlined,
} from "@ant-design/icons";
import { Flex, Tooltip, Typography, theme } from "antd";
import { useEffect, useState } from "react";
import { formatDateTime, formatTime, type VideoDetail } from "@/lib/api";
import { platformResults, postCount } from "@/lib/postResults";

// "posted": the post step once out somewhere, its words in green too.
type State = "done" | "posted" | "warn" | "todo" | "busy";

type Step = {
  key: string;
  label: string;
  state: State;
  /** What is true now, with its time when there is one. */
  detail: React.ReactNode;
  /** Where a click goes: a tab of the side panel. */
  tab?: "publish" | "post";
};

const HOUR = 3600_000;

/** A time within a day as "12 phút trước" / "sau 3 giờ", otherwise dd/mm/yyyy hh:mm, both in Vietnam time; the full
 * time is in the tooltip. */
export function When({ iso, now }: { iso: string; now: number }) {
  const diff = new Date(iso).getTime() - now;
  const away = Math.abs(diff);
  let text = formatDateTime(iso);
  if (away < 24 * HOUR) {
    const amount = away < HOUR ? `${Math.max(1, Math.round(away / 60_000))} phút` : `${Math.round(away / HOUR)} giờ`;
    text = diff < 0 ? `${amount} trước` : `sau ${amount}`;
  }
  return (
    <Tooltip title={formatDateTime(iso)}>
      <span>{text}</span>
    </Tooltip>
  );
}

function steps(video: VideoDetail, now: number): Step[] {
  const when = (iso: string) => <When iso={iso} now={now} />;
  const scenes = [...(video.title_scene ? [video.title_scene] : []), ...video.scenes];
  const withMedia = scenes.filter((scene) => scene.has_image || scene.video).length;
  const job = video.active_job;

  const script: Step = video.has_script
    ? { key: "script", label: "Kịch bản", state: "done", detail: video.script_at ? when(video.script_at) : "Đã có" }
    : job
      ? { key: "script", label: "Kịch bản", state: "busy", detail: "Đang viết" }
      : { key: "script", label: "Kịch bản", state: "todo", detail: "Chưa có" };

  const media: Step = {
    key: "media",
    label: "Ảnh",
    state: !video.has_script ? "todo" : withMedia === scenes.length ? "done" : "warn",
    detail: video.has_script ? `${withMedia}/${scenes.length} cảnh` : "—",
  };

  const mp4 = video.mp4;
  const render: Step =
    job?.kind === "render"
      ? { key: "render", label: "Render", state: "busy", detail: "Đang render", tab: "publish" }
      : mp4 && video.mp4_outdated
        ? {
            key: "render",
            label: "Render",
            state: "warn",
            detail: <>MP4 cũ hơn bản sửa, render lại ({when(mp4.rendered_at)})</>,
            tab: "publish",
          }
        : mp4
          ? { key: "render", label: "Render", state: "done", detail: when(mp4.rendered_at), tab: "publish" }
          : { key: "render", label: "Render", state: "todo", detail: "Chưa có MP4", tab: "publish" };

  // "X/Y nền tảng · hh:mm": the platforms it is out on, of those tried, and when the newest went out; in green.
  const results = platformResults(video);
  const count = postCount(results);
  const scheduled = video.publications
    .filter((post) => post.status === "scheduled" && post.scheduled_at)
    .map((post) => post.scheduled_at!)
    .sort();
  const suggested = video.plan_idea?.suggested_post_at;
  const post: Step = count.out
    ? {
        key: "post",
        label: "Đăng",
        state: "posted",
        detail: (
          <>
            {count.out}/{count.tried} nền tảng{count.last ? ` · ${formatTime(count.last)}` : ""}
            {scheduled.length > 0 && <>, hẹn {when(scheduled[0])}</>}
          </>
        ),
        tab: "publish",
      }
    : scheduled.length
      ? { key: "post", label: "Đăng", state: "done", detail: <>Hẹn {when(scheduled[0])}</>, tab: "publish" }
      : {
          key: "post",
          label: "Đăng",
          state: results.some((result) => result.state === "err") ? "warn" : "todo",
          detail: suggested ? <>Chưa đăng, kế hoạch gợi ý {when(suggested)}</> : "Chưa đăng",
          tab: "publish",
        };

  const products = video.affiliate_product_ids.length;
  const affiliate: Step = {
    key: "affiliate",
    label: "Affiliate",
    state: products ? "done" : "warn",
    detail: products ? `${products} sản phẩm` : "Chưa gắn sản phẩm",
    tab: "post",
  };

  const result: Step[] = [script, media, render, post, affiliate];
  // The 48-hour reading of the first Facebook post that went out: when it comes, then what it said.
  const first = video.publications
    .filter((row) => row.status === "published")
    .sort((a, b) => a.at.localeCompare(b.at))[0];
  if (first) {
    const read = first.metrics.at_48h;
    const due = new Date(new Date(first.at).getTime() + 48 * HOUR).toISOString();
    result.push(
      read
        ? {
            key: "48h",
            label: "48 giờ",
            state: "done",
            detail: (
              <>
                {(read.views ?? 0).toLocaleString("vi-VN")} view, đo {when(read.measured_at)}
              </>
            ),
            tab: "publish",
          }
        : {
            key: "48h",
            label: "48 giờ",
            state: "todo",
            detail: new Date(due).getTime() > now ? <>Đọc số {when(due)}</> : "Đang chờ đọc số",
            tab: "publish",
          },
    );
  }
  return result;
}

/** Where the video stands, one step after another with its time, under the title; a step with a tab opens it. */
export default function VideoProgress({
  video,
  onOpenTab,
}: {
  video: VideoDetail;
  onOpenTab: (tab: "publish" | "post") => void;
}) {
  const { token } = theme.useToken();
  // The relative times move on by themselves.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);

  const icon: Record<State, React.ReactNode> = {
    done: <CheckCircleFilled style={{ color: token.colorSuccess }} />,
    posted: <CheckCircleFilled style={{ color: token.colorSuccess }} />,
    warn: <ExclamationCircleFilled style={{ color: token.colorWarning }} />,
    todo: <ClockCircleOutlined style={{ color: token.colorTextTertiary }} />,
    busy: <LoadingOutlined style={{ color: token.colorInfo }} />,
  };

  return (
    <Flex wrap align="center" gap="4px 8px" style={{ marginTop: 8, fontSize: 13 }} data-testid="video-progress">
      {steps(video, now).map((step, index) => (
        <Flex key={step.key} align="center" gap={8}>
          {index > 0 && <RightOutlined style={{ fontSize: 10, color: token.colorTextQuaternary }} />}
          <Flex
            align="center"
            gap={6}
            data-testid={`progress-${step.key}`}
            data-state={step.state}
            // A link, not a button: it only moves to a tab, and the "Render" button keeps its name to itself.
            role={step.tab ? "link" : undefined}
            tabIndex={step.tab ? 0 : undefined}
            onClick={step.tab ? () => onOpenTab(step.tab!) : undefined}
            onKeyDown={step.tab ? (event) => event.key === "Enter" && onOpenTab(step.tab!) : undefined}
            style={{ cursor: step.tab ? "pointer" : undefined, padding: "2px 4px", borderRadius: 6 }}
          >
            {icon[step.state]}
            <Typography.Text strong style={{ fontSize: 13 }}>
              {step.label}
            </Typography.Text>
            <Typography.Text
              type={step.state === "warn" ? "warning" : step.state === "posted" ? "success" : "secondary"}
              style={{ fontSize: 13, whiteSpace: "nowrap" }}
            >
              {step.detail}
            </Typography.Text>
          </Flex>
        </Flex>
      ))}
    </Flex>
  );
}
