import "@fontsource/source-serif-4/400.css";
import "@fontsource/source-serif-4/400-italic.css";
import "@fontsource/source-serif-4/500.css";
import "@fontsource/source-serif-4/600.css";
import "@fontsource/noto-serif-devanagari/400.css";
import "@fontsource/noto-serif-devanagari/600.css";
import "@fontsource/noto-serif-kannada/400.css";
import "@fontsource/noto-serif-kannada/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "./globals.css";

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { Masthead } from "@/components/Masthead";

export const metadata: Metadata = {
  title: { default: "HeritageRec", template: "%s · HeritageRec" },
  description:
    "Does graph structure beat text for Indian heritage retrieval? The corpus, the knowledge graph and every ranking, shown as it is computed.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f2ede2" },
    { media: "(prefers-color-scheme: dark)", color: "#15140f" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Masthead />
        <main id="main">{children}</main>
        <footer className="page" style={{ paddingBottom: "3rem", color: "var(--ink-faint)", fontSize: "var(--step--1)" }}>
          <hr />
          Every number on these pages is read from a file a script produced; the Ledger lists them. Parts that are
          not built say so.
        </footer>
      </body>
    </html>
  );
}
