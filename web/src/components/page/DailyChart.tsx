"use client";

import EmptyState from "@/components/EmptyState";
import { Button, Flex, Table, Typography } from "antd";
import { useEffect, useState, type MouseEvent } from "react";
import { COLORS } from "@/app/theme";

// Drawn at the width it is shown, so its 11 px text stays 11 px on any screen.
const DEFAULT_WIDTH = 720;
const HEIGHT = 240;
const PAD = { left: 52, right: 14, top: 14, bottom: 28 };
// Under the plot, a row for the marks of the days with a post.
const POSTS_ROW = 18;
// About one date label per 110 px.
const LABEL_WIDTH = 110;

/** "05/11" from "2026-11-05": a day of the period, already in Vietnam time. */
export function shortDay(day: string): string {
  const [, month, date] = day.split("-");
  return `${date}/${month}`;
}

/** A round top for the y axis and its step: 0, step, 2·step… up to at least `max`. */
function scale(max: number): { top: number; step: number } {
  if (max <= 0) return { top: 4, step: 1 };
  const rough = max / 4;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 5, 10].map((n) => n * power).find((n) => n >= rough) ?? 10 * power;
  return { top: Math.max(step, Math.ceil(max / step) * step), step };
}

const compact = new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 1 });

/**
 * One number of a Page day by day, as a line over a light area: the days Facebook gave no number are a gap, not a 0.
 * Hovering a day shows its value (and its posts when `posts` is given and shown). A table of the same numbers is one
 * click away, for reading exact values.
 */
export default function DailyChart({
  label,
  days,
  values,
  format,
  posts,
  emptyText = "Chưa có số liệu trong khoảng này",
  testId,
}: {
  /** What the line is, for the tooltip, the table and screen readers. */
  label: string;
  days: string[];
  values: (number | null)[];
  format: (value: number | null) => string;
  /** The app's posts on each day; given, a mark sits under each day with one. */
  posts?: number[];
  emptyText?: string;
  testId?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const [frame, setFrame] = useState<HTMLDivElement | null>(null);
  const [WIDTH, setWidth] = useState(DEFAULT_WIDTH);
  useEffect(() => {
    if (!frame) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.round(entry.contentRect.width))));
    observer.observe(frame);
    return () => observer.disconnect();
  }, [frame]);
  const known = values.filter((value): value is number => value !== null);
  if (known.length === 0) {
    return (
      <div data-testid={testId}>
        <EmptyState description={emptyText} />
      </div>
    );
  }

  const bottom = HEIGHT - PAD.bottom - (posts ? POSTS_ROW : 0);
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = bottom - PAD.top;
  const { top, step } = scale(Math.max(...known));
  const x = (index: number) => PAD.left + (days.length > 1 ? (index * plotWidth) / (days.length - 1) : plotWidth / 2);
  const y = (value: number) => PAD.top + (1 - value / top) * plotHeight;

  // Runs of days with a number, each drawn as its own line and area.
  const runs: number[][] = [];
  values.forEach((value, index) => {
    if (value === null) return;
    const last = runs[runs.length - 1];
    if (last && last[last.length - 1] === index - 1) last.push(index);
    else runs.push([index]);
  });
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, n) => n * step);
  const every = Math.max(1, Math.ceil(days.length / Math.max(2, Math.floor(WIDTH / LABEL_WIDTH))));

  function onMove(event: MouseEvent<SVGSVGElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const at = ((event.clientX - box.left) / box.width) * WIDTH;
    const index = days.length > 1 ? Math.round(((at - PAD.left) / plotWidth) * (days.length - 1)) : 0;
    setHover(Math.min(Math.max(index, 0), days.length - 1));
  }

  const hovered = hover !== null ? values[hover] : null;
  return (
    <div data-testid={testId}>
      <div ref={setFrame} style={{ position: "relative" }}>
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          width="100%"
          role="img"
          aria-label={`Biểu đồ ${label.toLowerCase()} theo ngày`}
          style={{ display: "block", touchAction: "pan-y" }}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={PAD.left}
                x2={WIDTH - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
                stroke={COLORS.border}
                strokeDasharray={tick === 0 ? undefined : "2 4"}
              />
              <text x={PAD.left - 8} y={y(tick) + 4} textAnchor="end" fontSize={11} fill={COLORS.textSecondary}>
                {compact.format(tick)}
              </text>
            </g>
          ))}
          {days.map((day, index) =>
            (index % every === 0 && days.length - 1 - index >= every / 2) || index === days.length - 1 ? (
              <text
                key={day}
                x={x(index)}
                y={HEIGHT - 8}
                textAnchor={index === 0 ? "start" : index === days.length - 1 ? "end" : "middle"}
                fontSize={11}
                fill={COLORS.textSecondary}
              >
                {shortDay(day)}
              </text>
            ) : null,
          )}
          {runs.map((run) => {
            const line = run.map((index) => `${x(index).toFixed(1)},${y(values[index] as number).toFixed(1)}`);
            const area = `${x(run[0]).toFixed(1)},${y(0)} ${line.join(" ")} ${x(run[run.length - 1]).toFixed(1)},${y(0)}`;
            return (
              <g key={run[0]}>
                {run.length > 1 && <polygon points={area} fill={COLORS.primaryBg} />}
                {run.length > 1 ? (
                  <polyline
                    points={line.join(" ")}
                    fill="none"
                    stroke={COLORS.brand}
                    strokeWidth={2}
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                ) : (
                  <circle cx={x(run[0])} cy={y(values[run[0]] as number)} r={4} fill={COLORS.brand} />
                )}
              </g>
            );
          })}
          {posts?.map((count, index) =>
            count > 0 ? (
              <circle
                key={days[index]}
                data-testid="post-mark"
                cx={x(index)}
                cy={bottom + POSTS_ROW / 2 + 2}
                r={4}
                fill={COLORS.textSecondary}
                stroke={COLORS.surface}
                strokeWidth={2}
              />
            ) : null,
          )}
          {hover !== null && (
            <g pointerEvents="none">
              <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={bottom} stroke={COLORS.textSecondary} />
              {hovered !== null && (
                <circle
                  cx={x(hover)}
                  cy={y(hovered)}
                  r={5}
                  fill={COLORS.brand}
                  stroke={COLORS.surface}
                  strokeWidth={2}
                />
              )}
            </g>
          )}
        </svg>
        {hover !== null && (
          <div
            role="tooltip"
            data-testid="chart-tooltip"
            style={{
              position: "absolute",
              top: 4,
              left: `${(x(hover) / WIDTH) * 100}%`,
              transform: `translateX(${hover > days.length / 2 ? "calc(-100% - 10px)" : "10px"})`,
              background: COLORS.surface,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 8,
              padding: "6px 10px",
              pointerEvents: "none",
              whiteSpace: "nowrap",
              fontSize: 12,
            }}
          >
            <div style={{ color: COLORS.textSecondary }}>{shortDay(days[hover])}</div>
            <div>
              {label}: <strong>{format(hovered)}</strong>
            </div>
            {posts && posts[hover] > 0 && <div style={{ color: COLORS.textSecondary }}>{posts[hover]} bài đăng</div>}
          </div>
        )}
      </div>
      <Flex justify="space-between" align="center" gap={8} wrap>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {posts ? "Chấm xám dưới trục: ngày có bài app đăng." : " "}
        </Typography.Text>
        <Button type="link" size="small" onClick={() => setTable((open) => !open)}>
          {table ? "Ẩn bảng" : "Xem bảng"}
        </Button>
      </Flex>
      {table && (
        <Table
          size="small"
          rowKey="day"
          pagination={false}
          scroll={{ y: 280 }}
          dataSource={days.map((day, index) => ({ day, value: values[index], posts: posts?.[index] ?? 0 })).reverse()}
          columns={[
            { title: "Ngày", dataIndex: "day", render: (day: string) => day.split("-").reverse().join("/") },
            { title: label, dataIndex: "value", render: format },
            ...(posts ? [{ title: "Bài đăng", dataIndex: "posts" }] : []),
          ]}
        />
      )}
    </div>
  );
}
