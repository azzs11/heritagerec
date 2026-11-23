import "@fontsource/noto-sans/400.css";
import "@fontsource/noto-sans/500.css";
import "@fontsource/noto-sans/600.css";
import "@fontsource/noto-sans/700.css";
import "@fontsource/noto-sans-devanagari/400.css";
import "@fontsource/noto-sans-devanagari/600.css";
import "@fontsource/noto-sans-kannada/400.css";
import "@fontsource/noto-sans-kannada/600.css";
import "@fontsource/noto-serif/400.css";
import "@fontsource/noto-serif/400-italic.css";
import "@fontsource/noto-serif/600.css";
import "@fontsource/noto-serif-devanagari/400.css";
import "@fontsource/noto-serif-devanagari/600.css";
import "@fontsource/noto-serif-kannada/400.css";
import "@fontsource/noto-serif-kannada/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "./globals.css";

import type { Metadata, Viewport } from "next";
import { ViewTransition, type ReactNode } from "react";

import { Masthead } from "@/components/Masthead";
import { MotionRoot } from "@/components/MotionRoot";
import { SkyField } from "@/components/SkyField";
import { Trail } from "@/components/Wayfinding";

export const metadata: Metadata = {
  title: { default: "HeritageRec", template: "%s · HeritageRec" },
  description:
    "Does graph structure beat text for Indian heritage retrieval? The corpus, the knowledge graph and every ranking, shown as it is computed.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f1ea" },
    { media: "(prefers-color-scheme: dark)", color: "#141310" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <MotionRoot>
        <SkyField />
        <Masthead />
        <Trail />
        <main id="main">
          {/* Navigations are transitions in the App Router, so pages fade and rise in; the masthead stays still. */}
          <ViewTransition default="page">{children}</ViewTransition>
        </main>
        <footer className="page" style={{ paddingTop: 0, paddingBottom: "2rem", color: "var(--ink-faint)", fontSize: "var(--step--1)" }}>
          <hr />
          Code under Apache-2.0. Each document keeps its source&apos;s licence; images are shown from the museums&apos; own
          servers under their open licences.
        </footer>
        </MotionRoot>
      </body>
    </html>
  );
}
