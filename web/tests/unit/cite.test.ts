import { describe, expect, it } from "vitest";

import { bibtex, plainCitation } from "@/lib/cite";

const wiki = {
  id: "wikipedia:en:7051661",
  title: "Chennakeshava Temple, Belur",
  source: "wikipedia",
  url: "https://en.wikipedia.org/wiki/Chennakeshava_Temple,_Belur",
  licence: "https://creativecommons.org/licenses/by-sa/4.0/",
  fetched_at: "2026-11-19T10:00:00+00:00",
  language: "en",
};

const object = {
  ...wiki,
  id: "artic:100487",
  title: "Shah Inayat Allah of Sind, 50% & more",
  source: "artic",
  url: "https://www.artic.edu/artworks/100487",
  licence: "https://creativecommons.org/publicdomain/zero/1.0/",
};

describe("citations", () => {
  it("credits Wikipedia's contributors and its edition, with the retrieved date and the record", () => {
    const c = plainCitation(wiki);
    expect(c.startsWith("Wikipedia contributors. “Chennakeshava Temple, Belur.” English Wikipedia.")).toBe(true);
    expect(c).toContain("(retrieved 2026-11-19;");
    expect(c).toContain("record wikipedia:en:7051661.");
  });

  it("names a museum as the publisher and adds no author it does not know", () => {
    const c = plainCitation(object);
    expect(c.startsWith("“Shah Inayat Allah")).toBe(true);
    expect(c).toContain("Art Institute of Chicago.");
  });

  it("escapes BibTeX's special characters and builds a safe key", () => {
    const b = bibtex(object);
    expect(b.startsWith("@misc{heritagerec_artic_100487,")).toBe(true);
    expect(b).toContain("50\\% \\& more");
    expect(b).not.toContain("author");
    expect(bibtex(wiki)).toContain("author = {{Wikipedia contributors}}");
  });
});

import { rankingCsv } from "@/app/cases/model";

describe("ranking export", () => {
  it("writes both lenses with a header and quotes fields that need it", () => {
    const row = { id: "d1", rank: 1, score: 2.5, title: 'Temple, "old"', language: "en", source: "wikipedia", kind: "site" };
    const csv = rankingCsv("Belur", "bm25", "pagerank(hub=1, restart=0.15)", [row], [{ ...row, id: "d2", score: 0.1 }]);
    const lines = csv.trim().split("\n");
    expect(lines[0]).toBe("query,lens,system,rank,doc_id,title,language,source,kind,score");
    expect(lines[1]).toBe('Belur,text,bm25,1,d1,"Temple, ""old""",en,wikipedia,site,2.5');
    expect(lines[2]).toContain('graph,"pagerank(hub=1, restart=0.15)",1,d2');
  });
});

import { centuryText } from "@/components/Portrait";

describe("portrait text", () => {
  it("writes centuries as readers say them, and says when none is recorded", () => {
    expect(centuryText([])).toBe("no recorded century");
    expect(centuryText([20])).toBe("20th century");
    expect(centuryText([-3, 1, 3])).toBe("3rd century BCE to 3rd century");
    expect(centuryText([11, 12, 13])).toBe("11th century to 13th century");
    expect(centuryText([21, 22])).toBe("21st century to 22nd century");
  });
});
