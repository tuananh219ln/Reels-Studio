"use client";

import { Tabs } from "antd";
import PostedVideos from "@/components/affiliate/PostedVideos";
import Products from "@/components/affiliate/Products";
import Revenue from "@/components/affiliate/Revenue";
import PageHeader from "@/components/PageHeader";

export default function AffiliatePage() {
  return (
    <>
      <PageHeader
        title="Affiliate"
        description="Gắn sản phẩm vào video đã đăng, quản lý danh sách sản phẩm và xem doanh thu của bạn."
      />
      <Tabs
        destroyOnHidden
        items={[
          { key: "videos", label: "Video đã đăng", children: <PostedVideos /> },
          { key: "products", label: "Sản phẩm", children: <Products /> },
          { key: "revenue", label: "Doanh thu", children: <Revenue /> },
        ]}
      />
    </>
  );
}
