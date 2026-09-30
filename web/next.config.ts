import type { NextConfig } from "next";

// In development the FastAPI backend runs separately (uv run uvicorn winback.api:app).
const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8010";

const nextConfig: NextConfig = {
  compress: false, // keep the server-sent event stream unbuffered through the proxy
  async rewrites() {
    return process.env.NODE_ENV === "development"
      ? [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }]
      : [];
  },
};

export default nextConfig;
