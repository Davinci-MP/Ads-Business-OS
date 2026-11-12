"use client";

import { useState, useEffect } from "react";
import { API_BASE } from "../../lib/api";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    // Check if already logged in
    const storedToken = localStorage.getItem("adsos_auth_token");
    const storedUser = localStorage.getItem("adsos_auth_user");
    if (storedToken && storedUser) {
      // Already authenticated, redirect to accounts
      setTimeout(() => {
        window.location.href = "/accounts";
      }, 500);
    }
  }, []);

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        credentials: "include",
      });
      const data = await res.json();
      if (res.ok) {
        localStorage.setItem("adsos_auth_token", data.access_token);
        localStorage.setItem("adsos_auth_user", JSON.stringify(data.user));
        window.location.href = "/accounts";
      } else {
        setError(data.detail || "Đăng nhập thất bại");
      }
    } catch (e) {
      setError("Lỗi kết nối đến server");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "20px",
        background: "#121214",
        color: "#FFF",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      <div
        style={{
          background: "#3F3F3F",
          border: "1.5px solid currentColor",
          borderRadius: "8px",
          padding: "40px",
          maxWidth: "420px",
          width: "100%",
          boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
        }}
      >
        <h2
          style={{
            margin: "0 0 20px",
            fontSize: "1.5rem",
            fontWeight: 600,
            color: "#F3F4F6",
            textAlign: "center",
          }}
        >
          ADSOS BUSINESS OS
        </h2>
        <h3
          style={{
            margin: "0 0 20px",
            fontSize: "1rem",
            fontWeight: 500,
            color: "#888",
            textAlign: "center",
          }}
        >
          Đăng nhập hệ thống
        </h3>

        {error && (
          <div
            style={{
              marginBottom: "16px",
              padding: "8px",
              background: "#ffe0e0",
              borderRadius: "4px",
              textAlign: "center",
            }}
          >
            {error}
          </div>
        )}

        <form style={{ marginBottom: "24px" }} onSubmit={handleLogin}>
          <div style={{ marginBottom: "16px" }}>
            <label
              style={{
                display: "block",
                marginBottom: "6px",
                fontSize: "0.875rem",
              }}
            >
              Tên đăng nhập
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={{
                width: "100%",
                padding: "8px 12px",
                border: "1px solid currentColor",
                borderRadius: "4px",
                background: "transparent",
                color: "#FFF",
                fontSize: "1rem",
              }}
              required
            />
          </div>
          <div style={{ marginBottom: "24px" }}>
            <label
              style={{
                display: "block",
                marginBottom: "6px",
                fontSize: "0.875rem",
              }}
            >
              Mật khẩu
            </label>
            <div style={{ position: "relative" }}>
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  border: "1px solid currentColor",
                  borderRadius: "4px",
                  background: "transparent",
                  color: "#FFF",
                  fontSize: "1rem",
                  // password show/hide toggle will be added below
                }}
                required
              />
              <button
                type="button"
                style={{
                  position: "absolute",
                  right: "12px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "transparent",
                  border: "none",
                  color: "#666",
                  fontSize: "0.8rem",
                  cursor: "pointer",
                  padding: "0 4px",
                }}
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? "Ẩn" : "Hiện"}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            style={{
              width: "100%",
              padding: "10px",
              background: "#3b82f6",
              color: "#FFF",
              border: "none",
              borderRadius: "4px",
              fontSize: "1rem",
              fontWeight: 500,
              cursor: "pointer",
              transition: "background 0.2s",
            }}
          >
            {isLoading ? "Đang đăng nhập..." : "Đăng nhập"}
          </button>
        </form>

        <div style={{ marginTop: "20px", textAlign: "center", fontSize: "0.75rem", color: "#666" }}>
          <span>Chưa có tài khoản?</span> <a href="/register" style={{ color: "#3b82f6", textDecoration: "none" }}>Đăng ký</a>
        </div>

        <div
          style={{ marginTop: "20px", marginBottom: "10px", fontSize: "0.75rem", color: "#666" }}
        >
          <a href="/password-reset" style={{ color: "#3b82f6", textDecoration: "none" }}>
            Lấy lại mật khẩu
          </a>
        </div>

        <div style={{ marginTop: "20px", fontSize: "0.75rem", color: "#666" }}>
          <a href="/" style={{ color: "#666", textDecoration: "none" }}>
            Quay về AdsOS
          </a>
        </div>
      </div>
    </div>
  );
}
