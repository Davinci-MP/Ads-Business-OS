/** @type {import('next').NextConfig} */
// Trên Vercel (VERCEL=1) bắt buộc dùng thư mục build mặc định ".next" — Vercel tìm đúng ".next".
// Local: build tách sang ".next-build" để không đụng cache của dev server (".next") đang chạy.
const isVercel = !!process.env.VERCEL;
const nextConfig = {
  reactStrictMode: true,
  distDir: isVercel
    ? ".next"
    : process.env.NODE_ENV === "development"
      ? ".next"
      : ".next-build",
};

export default nextConfig;
