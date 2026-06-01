/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // Server-side proxy so the browser only ever talks to the frontend origin.
    // This sidesteps cross-origin Basic Auth prompts and CORS entirely.
    const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${backendUrl}/health`,
      },
    ];
  },
};

export default nextConfig;
