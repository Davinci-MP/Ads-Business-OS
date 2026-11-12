"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function RootPage() {
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("adsos_auth_token");
    const storedUser = localStorage.getItem("adsos_auth_user");
    router.replace(token && storedUser ? "/accounts" : "/login");
  }, [router]);

  return <p className="loading">Đang chuyển trang…</p>;
}
