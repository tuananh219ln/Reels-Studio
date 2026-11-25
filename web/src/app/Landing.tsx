"use client";

import { Button, Card, Flex, Typography } from "antd";
import Link from "next/link";
import Logo from "@/components/Logo";

/** What a visitor with no account sees at `/`. English on purpose: it mirrors the app description registered with
 * TikTok, which reviewers read. Static: no API call and no user data. */
export default function Landing() {
  return (
    <Flex justify="center" style={{ minHeight: "100vh", padding: "64px 16px", boxSizing: "border-box" }}>
      <Flex vertical gap={32} style={{ width: "100%", maxWidth: 640 }} lang="en">
        <Logo size={20} />
        <Flex vertical gap={12}>
          <Typography.Title level={1} style={{ margin: 0 }}>
            Reels Studio
          </Typography.Title>
          <Typography.Paragraph style={{ fontSize: 18, margin: 0 }}>
            Reels Studio is a web app that helps creators make short vertical videos (9:16) and publish them to TikTok.
          </Typography.Paragraph>
        </Flex>
        <Card>
          <Typography.Title level={4} style={{ marginTop: 0 }}>
            How it works
          </Typography.Title>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li>A creator writes a script, adds scene footage and renders a vertical 9:16 video.</li>
            <li>
              The creator can connect their own TikTok account with TikTok Login Kit. We read only the basic profile
              (name and avatar) to show which account is connected.
            </li>
            <li>
              A video is sent to that account only when the creator chooses to post it: as a draft in their TikTok
              inbox, or published directly after they review the post settings.
            </li>
          </ul>
        </Card>
        <Flex gap={16} align="center" wrap>
          <Button type="primary" size="large" href="/login" lang="vi">
            Đăng nhập
          </Button>
          <Typography.Text type="secondary">
            <Link href="/privacy">Privacy Policy</Link> · <Link href="/terms">Terms of Service</Link>
          </Typography.Text>
        </Flex>
      </Flex>
    </Flex>
  );
}
