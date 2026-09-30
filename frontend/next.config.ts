import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // pin the workspace root so a stray lockfile elsewhere (e.g. in $HOME) is ignored
  turbopack: { root: path.join(__dirname) },
};

export default nextConfig;
