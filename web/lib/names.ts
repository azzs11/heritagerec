// Display names for codes used in the records. Names only: no counts live here.

export const SOURCES: Record<string, string> = {
  wikipedia: "Wikipedia",
  cleveland: "Cleveland Museum of Art",
  met: "The Metropolitan Museum of Art",
  artic: "Art Institute of Chicago",
  internet_archive: "Internet Archive",
  wellcome: "Wellcome Collection",
};

export const LANGUAGES: Record<string, string> = { en: "English", hi: "Hindi · हिन्दी", kn: "Kannada · ಕನ್ನಡ" };

export const DOC_TYPES: Record<string, string> = {
  site: "Sites and monuments",
  object: "Museum objects",
  person_dynasty_style: "People, dynasties and styles",
  culture: "Living culture",
  manuscript_text: "Manuscripts and books",
  inscription: "Inscriptions",
};

export const KINDS: Record<string, string> = {
  document: "document",
  entity: "entity",
  connector: "connector",
  period: "century",
};

export const KINDS_PLURAL: Record<string, string> = {
  document: "documents",
  entity: "entities",
  connector: "connectors",
  period: "centuries",
};

// Result files kept from the conference version; shown, but never as evidence (see results/README.md, legacy/).
export const SUPERSEDED: Record<string, string> = {
  "results/evaluation_report.json": "conference version, superseded: one evaluated query and a circular ground truth",
};

export function rowsOf(counts: Record<string, number>, names: Record<string, string>) {
  return Object.entries(counts)
    .map(([key, value]) => ({ key, label: names[key] ?? key, value }))
    .sort((a, b) => b.value - a.value);
}
