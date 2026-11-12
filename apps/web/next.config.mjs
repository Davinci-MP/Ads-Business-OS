/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Tách sản phẩm build khỏi cache của máy chủ phát triển đang chạy.
  distDir: process.env.NODE_ENV === "development" ? ".next" : ".next-build",
};

export default nextConfig;
