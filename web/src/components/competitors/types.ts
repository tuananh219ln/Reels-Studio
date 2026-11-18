import type { CompetitorScan } from "@/lib/competitorScanner";

/** One row of GET /competitors (api competitors.list_competitors). */
export type Competitor = {
  id: number;
  fb_url: string;
  kind: "page" | "profile";
  /** The name the scan read; `custom_name` is the member's own and wins; `display_name` is what to show. */
  name: string | null;
  custom_name: string | null;
  display_name: string;
  handle: string | null;
  fb_id: string | null;
  avatar_url: string | null;
  is_verified: boolean;
  /** False until a scan has read the Page's header. */
  /** Which videos of a scan are kept: auto (a big channel keeps only 100K+), all, 100k or 1m. */
  video_threshold_mode: "auto" | "all" | "100k" | "1m";
  has_meta: boolean;
  followers: number | null;
  reels_url: string;
  videos_url: string;
  /** Who scans it: the whole team reads it, only they scan it again, resume, rename or delete it. */
  owner: { id: number; name: string };
  is_mine: boolean;
  /** A header-only refresh ("Cập nhật thông tin kênh") is waiting or running. */
  meta_busy: boolean;
  latest_scan:
    | (CompetitorScan & {
        total_views: number;
        median_views: number | null;
        /** Videos read; `stored_count` of them are kept, from `threshold_applied` views (null: all kept). */
        video_count: number;
        stored_count: number;
        threshold_applied: number | null;
        reels_count: number;
        videos_count: number;
      })
    | null;
};

export type Stats = {
  videos: number;
  videos_with_views: number;
  total_views: number;
  median_views: number | null;
  buckets: { label: string; videos: number; views: number }[];
  top10_share: number | null;
  by_type: { reel: number; video: number };
  videos_per_week: number | null;
  frequency: { reel: Frequency | null; video: Frequency | null };
  newest_posted_at: string | null;
  oldest_posted_at: string | null;
  limits: string[];
};

/** How often one grid was posted to (api competitors._frequency): the whole span, and each stretch between dates. */
export type Frequency = {
  videos_per_week: number | null;
  from: string;
  to: string;
  videos: number;
  stretches: { from: string; to: string; videos: number; videos_per_week: number | null }[];
};

export type Report = {
  id: number;
  created_at: string | null;
  written_by: string;
  /** The member whose Claude saved it. */
  created_by: string | null;
  markdown: string;
};

export type ScanDetail = CompetitorScan & { stats: Stats; report: Report | null };

export type VideoRow = {
  rank: number;
  /** A small picture, only for the videos whose own page the extension opened. */
  thumb_url: string | null;
  fb_video_id: string;
  url: string;
  views: number | null;
  caption: string | null;
  audio_name: string | null;
  reactions: number | null;
  comments: number | null;
  shares: number | null;
  posted_at: string | null;
  posted_raw: string | null;
  type: "reel" | "video";
};

export type VideoPage = {
  scan_id: number | null;
  scanned_count: number;
  threshold_applied: number | null;
  total: number;
  videos: VideoRow[];
  has_engagement: boolean;
  has_published_at: boolean;
};
