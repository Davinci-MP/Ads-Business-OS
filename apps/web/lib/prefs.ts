"use client";

const PREFIX = "adsos.ui.";

export function loadPref(key: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  try {
    return window.localStorage.getItem(PREFIX + key) ?? fallback;
  } catch {
    return fallback;
  }
}

export function savePref(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    if (value === "") window.localStorage.removeItem(PREFIX + key);
    else window.localStorage.setItem(PREFIX + key, value);
  } catch {
    // localStorage có thể bị tắt; chỉ ghi nhớ lựa chọn là tính năng phụ.
  }
}
