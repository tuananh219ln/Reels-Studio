"use client";

import { Segmented } from "antd";

/** "Của tôi": the signed-in member's own rows; "Cả đội": everyone's. */
export type Whose = "mine" | "all";

/**
 * The "Của tôi / Cả đội" switch on every list of the team's work (brief docs/specs/chu-thuong-ca-nhan-hoa, the rule
 * over part B). Nothing is hidden from teammates: "Cả đội" always shows every row. The counts are left out where the
 * list is read a page at a time.
 */
export default function WhoseFilter({
  value,
  onChange,
  mine,
  all,
  mineLabel = "Của tôi",
  allLabel = "Cả đội",
  label = "Của ai",
}: {
  value: Whose;
  onChange: (next: Whose) => void;
  mine?: number;
  all?: number;
  /** "Của tôi" by default; "Tôi thêm" where a row is mine by who added it. */
  mineLabel?: string;
  /** "Cả đội" by default; "Tất cả" where the rows are Pages or products, not the team's work. */
  allLabel?: string;
  /** The group's accessible name. */
  label?: string;
}) {
  const count = (n: number | undefined) => (n === undefined ? "" : ` (${n})`);
  return (
    <Segmented<Whose>
      aria-label={label}
      value={value}
      onChange={onChange}
      options={[
        { value: "mine", label: `${mineLabel}${count(mine)}` },
        { value: "all", label: `${allLabel}${count(all)}` },
      ]}
    />
  );
}
