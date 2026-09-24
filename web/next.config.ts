import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle (.next/standalone) so the Docker image
  // can run without node_modules. See web/Dockerfile.
  output: "standalone",
};

export default nextConfig;
