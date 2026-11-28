"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Trang ADS CHECK cũ (dùng cookie, tự điền dữ liệu giả) đã thay bằng /adscheck
 * (quét qua Graph API chính thức). Giữ đường dẫn này để link cũ không gãy:
 * chuyển hướng sang /adscheck, giữ nguyên ?via_id=.
 */
export default function AdsCheckRedirect() {
  const router = useRouter();

  useEffect(() => {
    const viaId = new URLSearchParams(window.location.search).get("via_id");
    router.replace(viaId && /^\d+$/.test(viaId) ? `/adscheck?via_id=${viaId}` : "/adscheck");
  }, [router]);

  return (
    <div style={{ padding: "48px", textAlign: "center", color: "var(--muted)" }}>
      Đang chuyển sang trang ADS CHECK mới…
    </div>
  );
}
