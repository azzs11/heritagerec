import type { NextConfig } from "next";

// Exported as static files and served by the FastAPI server in the release (decision 0025),
// so nothing here may need a Node server at run time.
const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  // next dev otherwise writes an AGENTS.md of tool instructions into the project.
  agentRules: false,
};

export default config;
