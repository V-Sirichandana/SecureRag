import path from "path";
import { fileURLToPath } from "url";
import type { NextConfig } from "next";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // There is a stray lockfile in the parent directory; pin tracing to this project.
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
