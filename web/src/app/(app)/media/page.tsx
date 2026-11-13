"use client";
import MediaLibrary from "@/components/media/MediaLibrary";
import { Suspense } from "react";
export default function MediaPage() {
  return (
    <Suspense fallback={null}>
      <MediaLibrary />
    </Suspense>
  );
}
