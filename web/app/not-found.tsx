import Link from "next/link";

import { Notice } from "@/components/Wayfinding";

export const metadata = { title: "Not in the archive" };

export default function NotFound() {
  return (
    <div className="page">
      <Notice
        title="This page is not in the archive."
        actions={
          <>
            <Link href="/cases/">Search</Link>
            <Link href="/atlas/">Atlas</Link>
            <Link href="/graph/">Graph</Link>
            <Link href="/">Home</Link>
          </>
        }
      >
        <p>The address may be mistyped, or the page may have moved. Everything the site holds is reachable from here.</p>
      </Notice>
    </div>
  );
}
