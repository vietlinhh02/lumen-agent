import type { NextConfig } from "next";

// Define the backend URL. Fallback to localhost if not provided.
const backendUrl = process.env.BACKEND_URL ?? `http://127.0.0.1:${process.env.BACKEND_PORT ?? "8000"}`;

const nextConfig: NextConfig = {
  allowedDevOrigins: ["*"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      // Backwards-compat: older search sessions / external links may reference
      // PDFs via the absolute filesystem-style path (e.g. /data/papers/foo.pdf).
      // Map it to the same backend mount so the URL works in the browser.
      {
        source: "/data/papers/:path*",
        destination: `${backendUrl}/api/pdf-files/:path*`,
      },
    ];
  },
};

export default nextConfig;
