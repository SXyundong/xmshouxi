/** @type {import('next').NextConfig} */
const nextConfig = {
  // 前端通过 /api 反向代理到后端，避免 CORS，也无需在浏览器里暴露后端地址
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.BACKEND_URL || 'http://localhost:8000'}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
