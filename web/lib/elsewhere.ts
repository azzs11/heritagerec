// Where else to look when this archive does not hold what a reader asked for. Links only; nothing is fetched.

export interface Route {
  name: string;
  why: string;
  url: string;
}

export function elsewhere(q: string, lang: string): Route[] {
  const e = encodeURIComponent(q);
  const wiki = lang === "hi" || lang === "kn" ? lang : "en";
  const wikiName = { en: "English", hi: "Hindi", kn: "Kannada" }[wiki];
  return [
    { name: `Wikipedia (${wikiName})`, why: "articles beyond the ones collected here", url: `https://${wiki}.wikipedia.org/w/index.php?search=${e}` },
    { name: "Wikidata", why: "the facts this site's graph is built from, for everything", url: `https://www.wikidata.org/w/index.php?search=${e}` },
    { name: "Internet Archive", why: "old books, gazetteers and reports, often free to download", url: `https://archive.org/search?query=${e}` },
    { name: "The Met", why: "objects, many with open images", url: `https://www.metmuseum.org/art/collection/search?q=${e}` },
    { name: "Cleveland Museum of Art", why: "objects under CC0", url: `https://www.clevelandart.org/art/collection/search?search=${e}` },
  ];
}
