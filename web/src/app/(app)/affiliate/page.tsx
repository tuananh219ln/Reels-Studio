"use client";

import { Tabs, Typography } from "antd";
import PostedVideos from "@/components/affiliate/PostedVideos";
import Products from "@/components/affiliate/Products";

export default function AffiliatePage() {
  return (
    <>
      <Typography.Title level={2} style={{ marginTop: 0, fontWeight: 600 }}>
        Affiliate Shopee
      </Typography.Title>
      <Tabs
        destroyOnHidden
        items={[
          { key: "videos", label: "Video đã đăng", children: <PostedVideos /> },
          { key: "products", label: "Sản phẩm", children: <Products /> },
        ]}
      />
    </>
  );
}
