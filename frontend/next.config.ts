import type { NextConfig } from "next";

const backendPort = process.env.BACKEND_PORT ?? "8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `http://localhost:${backendPort}/api/:path*`,
      },
      // Backwards-compat: older search sessions / external links may reference
      // PDFs via the absolute filesystem-style path (e.g. /data/papers/foo.pdf).
      // Map it to the same backend mount so the URL works in the browser.
      {
        source: "/data/papers/:path*",
        destination: `http://localhost:${backendPort}/api/pdf-files/:path*`,
      },
    ];
  },
};

export default nextConfig;
