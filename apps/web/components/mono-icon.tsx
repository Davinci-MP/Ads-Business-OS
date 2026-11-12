import type { ReactNode, SVGProps } from "react";

export type MonoIconName =
  | "dashboard" | "account" | "business" | "via" | "customer" | "analytics"
  | "campaign" | "settings" | "search" | "menu" | "sun" | "moon" | "bell"
  | "close" | "copy" | "refresh" | "edit" | "trash" | "filter" | "export" | "check"
  | "chevron-left" | "chevron-right";

const paths: Record<MonoIconName, ReactNode> = {
  dashboard: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  account: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h10M7 13h6"/></>,
  business: <><path d="M4 21V8l8-4 8 4v13M8 11h2m4 0h2M8 15h2m4 0h2"/><path d="M10 21v-3h4v3"/></>,
  via: <><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></>,
  customer: <><circle cx="9" cy="8" r="3"/><path d="M3 20c.5-4 2.5-6 6-6s5.5 2 6 6M16 5c2 0 3 1.5 3 3s-1 3-3 3M17 14c2.5.5 3.5 2.5 4 5"/></>,
  analytics: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></>,
  campaign: <><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="m15 9 6-6"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.5-2.4 1A8 8 0 0 0 15 6l-.3-2.5h-4L10.5 6A8 8 0 0 0 9 7L6.5 6 4.5 9.5 6.5 11a7 7 0 0 0 0 2l-2 1.5 2 3.5L9 17a8 8 0 0 0 1.5 1l.2 2.5h4L15 18a8 8 0 0 0 1.5-1l2.4 1 2-3.5-2-1.5a7 7 0 0 0 .1-1Z"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16"/>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M19 5l-1.5 1.5m-11 11L5 19"/></>,
  moon: <path d="M20 15.5A8 8 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z"/>,
  bell: <><path d="M6 9a6 6 0 0 1 12 0c0 7 3 7 3 7H3s3 0 3-7Z"/><path d="M10 20h4"/></>,
  close: <path d="m6 6 12 12M18 6 6 18"/>,
  copy: <><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></>,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5"/><path d="M18 12a6 6 0 0 0-10-4L4 12m2 0a6 6 0 0 0 10 4l4-4"/></>,
  edit: <><path d="m14 5 5 5L9 20H4v-5Z"/><path d="m12 7 5 5"/></>,
  trash: <><path d="M4 7h16M9 3h6l1 4M7 7l1 14h8l1-14"/><path d="M10 11v6M14 11v6"/></>,
  filter: <path d="M3 5h18l-7 8v6l-4 2v-8Z"/>,
  export: <><path d="M12 3v12m0 0 4-4m-4 4-4-4M5 19h14"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  "chevron-left": <path d="m15 18-6-6 6-6"/>,
  "chevron-right": <path d="m9 18 6-6-6-6"/>,
};

export function MonoIcon({ name, ...props }: { name: MonoIconName } & SVGProps<SVGSVGElement>) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>{paths[name]}</svg>;
}
