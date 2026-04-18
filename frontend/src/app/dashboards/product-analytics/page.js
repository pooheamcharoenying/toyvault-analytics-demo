"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Product Analytics has been consolidated into Brands & Products.
 * This page redirects to /dashboards/brands (Product Classification tab).
 */
export default function ProductAnalyticsRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/dashboards/brands");
  }, [router]);
  return (
    <div className="flex items-center justify-center min-h-[50vh] text-gray-500">
      Redirecting to Brands &amp; Products...
    </div>
  );
}
