"use client";

import { Flex, Segmented, Select, Typography } from "antd";
import { clockChangeNote, DEFAULT_US_ZONE, isUs, US_ZONES, VN_ZONE } from "@/lib/scheduleZone";

/** The zone posting times are written in: VN | US, and which US zone. A note shows in the fortnight before the US
 * changes its clocks. */
export default function ScheduleZonePicker({
  value,
  onChange,
  label,
  disabled,
}: {
  value: string;
  onChange: (zone: string) => void;
  label: string;
  disabled?: boolean;
}) {
  const note = clockChangeNote(value);
  return (
    <Flex vertical gap={4}>
      <Flex gap={6} align="center" wrap>
        <Segmented
          size="small"
          aria-label={`Múi giờ lịch đăng của ${label}`}
          disabled={disabled}
          value={isUs(value) ? "US" : "VN"}
          options={[
            { value: "VN", label: "VN" },
            { value: "US", label: "US" },
          ]}
          onChange={(choice) => onChange(choice === "VN" ? VN_ZONE : isUs(value) ? value : DEFAULT_US_ZONE)}
        />
        {isUs(value) && (
          <Select
            size="small"
            aria-label={`Múi giờ Mỹ của ${label}`}
            disabled={disabled}
            value={value}
            style={{ width: 150 }}
            options={US_ZONES.map((zone) => ({ value: zone.value, label: zone.label }))}
            onChange={onChange}
          />
        )}
      </Flex>
      {note && (
        <Typography.Text type="warning" style={{ fontSize: 12 }} data-testid="clock-change-note">
          {note}
        </Typography.Text>
      )}
    </Flex>
  );
}
