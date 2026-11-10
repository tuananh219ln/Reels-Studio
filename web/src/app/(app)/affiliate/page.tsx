"use client";

import { Tabs } from "antd";
import { Suspense } from "react";
import PostedVideos from "@/components/affiliate/PostedVideos";
import Products from "@/components/affiliate/Products";
import Revenue from "@/components/affiliate/Revenue";
import PageHeader from "@/components/PageHeader";
import { useUrlChoice } from "@/lib/urlState";

type Tab = "videos" | "products" | "revenue";

export default function AffiliatePage() {
  // The tab and its list's search and filters are in the address, which a static page only knows in the browser.
  return (
    <Suspense fallback={null}>
      <Affiliate />
    </Suspense>
  );
}

function Affiliate() {
  const [tab, setTab] = useUrlChoice<Tab>("tab", "videos", ["products", "revenue"]);
  // Each tab has its own filters: a new tab starts with none of the last one's.
  const choose = (next: string) => {
    window.history.replaceState(null, "", window.location.pathname);
    setTab(next as Tab);
  };
  return (
    <>
      <PageHeader
        title="Affiliate"
        description="Gắn sản phẩm vào video đã đăng, quản lý danh sách sản phẩm và xem doanh thu của bạn."
      />
      <Tabs
        activeKey={tab}
        onChange={choose}
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
