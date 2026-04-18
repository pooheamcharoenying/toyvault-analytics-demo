"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Location Analytics has been consolidated into Locations & Stores.
 * This page redirects to /dashboards/locations.
 */
export default function LocationAnalyticsRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/dashboards/locations");
  }, [router]);
  return (
    <div className="flex items-center justify-center min-h-[50vh] text-gray-500">
      Redirecting to Locations &amp; Stores...
    </div>
  );
}
