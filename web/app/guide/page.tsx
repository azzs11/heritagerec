import Link from "next/link";

import s from "../pages.module.css";

export const metadata = { title: "Guide" };

export default function Guide() {
  return (
    <article className="page">
      <header className={s.head}>
        <p className={s.kicker}>Guide</p>
        <h1 className={s.title}>Five minutes with HeritageRec</h1>
        <p className={s.lede}>
          What the site does, a first case to walk through, how to run it on your own machine, and what to do when a part
          is missing.
        </p>
      </header>

      <h2 className={s.h2}>A first case, in five steps</h2>
      <ol className={s.steps}>
        <li>
          <div>
            <h3>Read the question on the front page</h3>
            <p>
              The <Link href="/">Story</Link> says what is being tested: whether a knowledge graph finds better documents
              than words alone. Every figure there names the file it was read from.
            </p>
          </div>
        </li>
        <li>
          <div>
            <h3>Open a case</h3>
            <p>
              Go to <Link href="/cases/?q=Hoysala%20temples%20Belur">Cases with “Hoysala temples Belur”</Link>. Step 1
              shows how the question was read: the words reduced to the forms the index stores (“temples” becomes
              “templ”).
            </p>
          </div>
        </li>
        <li>
          <div>
            <h3>Ask why a result is where it is</h3>
            <p>
              Under the first result, choose <em>why here? show the working</em>. Each word&apos;s share of the score is
              listed, and a seal says whether the shares add up to the score the search engine returned. Switch to BM25 +
              RM3 to see the words it adds.
            </p>
          </div>
        </li>
        <li>
          <div>
            <h3>Follow a result into the graph</h3>
            <p>
              In the graph lens column, choose an entity a result is about, such as the Hoysala Empire. The{" "}
              <Link href="/graph/?node=Q466581">neighbourhood</Link> shows its facts from Wikidata; choose a neighbour
              and <em>Path from the centre</em> to see how two things are joined, and whether only a hub joins them.
            </p>
          </div>
        </li>
        <li>
          <div>
            <h3>Walk to the place</h3>
            <p>
              On the <Link href="/atlas/?lat=13.16&lon=75.87">Atlas</Link>, the places nearest Belur appear with what ties
              them. Then open the <Link href="/lab/">Lab</Link> to see where the system already breaks, and the{" "}
              <Link href="/ledger/">Ledger</Link> to trace any number.
            </p>
          </div>
        </li>
      </ol>

      <h2 className={s.h2}>Run it on your machine</h2>
      <p>From the repository root, with uv, Node.js and (for search) Java 21 installed:</p>
      <pre className={s.code} tabIndex={0} aria-label="Commands to run the site">{`uv sync
uv run python -m server          # the server, on port 8000
cd web && npm ci && npm run dev  # the site, on http://localhost:3000`}</pre>
      <p className={s.small}>
        Without Java and the indexes, start the server with <code>--no-keyword</code>: the graph, atlas and ledger still
        work, and search says why it is unavailable.
      </p>

      <h2 className={s.h2}>When something is missing</h2>
      <div className={s.scroll} role="region" aria-label="Troubleshooting" tabIndex={0}>
      <table className={s.table}>
        <thead>
          <tr>
            <th scope="col">What you see</th>
            <th scope="col">Why</th>
            <th scope="col">What to do</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>“the interface server is not answering”</td>
            <td>The server is not running, or on another port</td>
            <td>
              <code>uv run python -m server</code>; the site expects it at <code>http://127.0.0.1:8000</code> during
              development
            </td>
          </tr>
          <tr>
            <td>keyword: “Java is not configured”</td>
            <td>No Java 21, or <code>JAVA_HOME</code> not in <code>.env</code></td>
            <td>Install a Java 21 JDK and set <code>JAVA_HOME</code> in <code>.env</code> (see <code>.env.example</code>)</td>
          </tr>
          <tr>
            <td>keyword: “the BM25 index … is missing”</td>
            <td>The indexes are built locally and are not in git</td>
            <td>
              <code>uv run python -m src.retrieval.bm25 index</code> (needs the passages:{" "}
              <code>uv run python -m src.retrieval.passages</code>)
            </td>
          </tr>
          <tr>
            <td>corpus: “… is not on this machine”</td>
            <td>The corpus snapshot is not kept in git</td>
            <td>Rebuild it from the raw responses, or download it at release; search still works without titles</td>
          </tr>
          <tr>
            <td>graph: “… is missing”</td>
            <td>The explorer files were not built</td>
            <td>
              <code>uv run python -m src.explorer.build</code>
            </td>
          </tr>
          <tr>
            <td>“not built yet”</td>
            <td>That system is planned and has a decision record, but does not exist yet</td>
            <td>Nothing to fix: the seal names the record that describes it</td>
          </tr>
          <tr>
            <td>A port is in use</td>
            <td>Another program holds 8000 or 3000</td>
            <td>
              <code>uv run python -m server --port 8010</code>, then start the site with{" "}
              <code>NEXT_PUBLIC_API_BASE=http://127.0.0.1:8010 npm run dev</code>
            </td>
          </tr>
        </tbody>
      </table>
      </div>
    </article>
  );
}
