# 0031: Coverage and selection bias: measure it, cut the part we add, report results by coverage

- Status: accepted (author, 2026-11-23: "we cover the coverage and selection bias, if you have better idea we
  do that"). The six steps come from the plan; the changes listed under "Changes to the plan's version" were
  delegated to this record.
- Date: 2026-11-23
- Amends: 0002 (ASI stratum language rule), 0015 (ASI remainder language rule), 0021 (tier quota for the
  queries). Specification Section 3 ("Coverage and selection bias") and Section 9.

## Context

Every document enters through a Wikidata entity, so the corpus can only hold heritage that Wikidata already
describes. That coverage is uneven, and three biases follow:

- **Coverage bias.** Famous sites with English documentation have items, articles and many links. Village
  temples, local inscriptions and folk traditions in Karnataka and the Hindi belt have less coverage or none,
  and Hindi and Kannada labels are often missing.
- **Filter bias, added by our own rules.** The ASI stratum (0002) and the ASI remainder (0015) require an
  English article, so a monument with only a Hindi or Kannada article never enters. The class-based list (0018)
  already accepts articles in any of the three languages.
- **A confound with RQ1.** Entities with rich coverage also have the densest graph neighbourhoods. If the test
  set leans towards them, "graph beats text" may only mean "graph beats text where Wikidata is rich".

What is already in place: the core graph's raw responses (`data/raw/graph_core_v1/`) carry each entity's
`lastrevid` and `modified` time (decision 0020). So the Wikidata state behind the graph is fixed per entity by
revision, not by a dump.

Comparable work:

- Kaffee et al. (OpenSym 2017) measured label coverage by language in Wikidata and found most languages thinly
  covered.
- Graham et al. (2014) showed the uneven geography of Wikipedia content.
- Sciavolino et al. (EMNLP 2021, EntityQuestions) found that dense retrievers fail on questions about rare
  entities where BM25 holds up.
- Mallen et al. (ACL 2023, PopQA) reported results in popularity bins and showed that they change the
  conclusion.
- Kandpal et al. (ICML 2023) showed that LLMs know much less about long-tail entities.

That last finding matters for the LLM judge and for the LLM query generator, not only for the systems we
compare.

## Options considered

Gateway:

| Option | For | Against |
| --- | --- | --- |
| A. Wikidata as the only gateway, bias unmeasured | Simplest | The confound stays open; a reviewer's first objection |
| B. Wikidata as the gateway for the headline; measure the bias; report by coverage; a small off-Wikidata probe | Keeps language-independent IDs (RQ3) and CC0; turns the objection into a result | Adds an audit and a tier analysis |
| C. A second gateway (official lists, gazetteers) for the headline | Least biased corpus | Entities without IDs break RQ3 and the core graph; months of matching |

How coverage tiers are defined:

| Option | For | Against |
| --- | --- | --- |
| A. Tertiles of sitelink count and our graph degree (the plan's version) | Simple | Our degree changes whenever the graph build changes (relations, hubs), so the tiers move with system design |
| B. Tertiles of a Wikidata coverage score (total sitelinks and statement count, rank-averaged), fixed at the snapshot; our graph degree reported as a covariate | Independent of our build choices; computable from saved responses plus one sitelink fetch | Two variables combined into one rank |
| C. Page-view bins (PopQA style) | Precedent in QA | A new data source that changes daily; popularity is not coverage |
| D. Continuous only, no tiers | No arbitrary cut points | Harder to read in a table |

How the tier claim is tested:

| Option | For | Against |
| --- | --- | --- |
| A. RQ1 and RQ3 per tier, each tested separately (the plan's version) | Easy to read | Three separate tests do not test the confound itself: "graph wins in rich but not sparse" needs a test of the difference |
| B. A, plus an interaction test: is the per-query graph-minus-text NDCG@10 difference smaller in the sparse tier than in the rich tier (permutation test), plus a per-query regression of that difference on the continuous coverage score | Tests the confound directly; uses all queries | Secondary hypotheses to pre-register |

Audit sampling frame:

| Option | For | Against |
| --- | --- | --- |
| A. About 300 entries, half Karnataka, from the ASI, Karnataka state and UNESCO lists (the plan's version) | Matches the Kannada focus | The Hindi belt, named in the problem, is not measured |
| B. About 300 entries: about 150 Karnataka (ASI circles and the state list), about 100 Hindi-belt states (ASI circles and one state's own list), about 50 the rest of India (ASI); the UNESCO intangible list for India in full | Covers both languages of RQ3 | Needs one more state list |

## Decision

Gateway B, tiers B with D as the test variable, test B, sampling frame B. The six steps:

1. **Coverage audit.** The sample is a stratified random draw (seeded) from official lists built outside
   Wikidata and Wikipedia:
   - the ASI list of centrally protected monuments, by state and circle;
   - the Karnataka state-protected list;
   - one Hindi-belt state's protected list (chosen by what is published);
   - the UNESCO intangible heritage list for India, in full.

   Wikipedia "List of …" pages are not a frame, because the same community writes them. For each entry, record:
   Wikidata item (yes or no), ASI ID (P1371), articles in en, hi and kn, article length, statement count,
   sitelink count and graph degree. Record each list's source, version, date and licence.

   Matching is done by a script and confirmed by the author. A "no item" result needs a recorded search trail:
   name variants in three scripts, plus the place. A random 10% of the matches are checked a second time.
   Rates are reported with Wilson 95% intervals. Besides the sample, the full ASI list is compared with the
   corpus by state (the share of each state's monuments that are in the corpus).
2. **Drop the English-only filter.** A seed or ASI-remainder entity qualifies with an article in en, hi or kn,
   the same rule 0018 already uses. The seed sample and its random draw stay as they are. Monuments that qualify
   only through hi or kn go into a new list version (`asi_remainder_v2`). Report how many entities enter only
   through hi or kn, per list.
3. **Coverage tiers.** Each document entity gets a coverage score:
   - its total sitelinks and its statement count, each ranked, and the two ranks averaged;
   - computed once, on the frozen snapshot;
   - tertiles over all document entities give the tiers rich, middle and sparse.

   Each query gets the tier of its target entity. The author marks the target entity during curation, without
   seeing any system output. Queries with no target entity form a fourth group, "no entity".

   Quotas:
   - at least 30 of the 160 test queries are in the sparse tier, and at least 8 of the 40 dev queries, so that
     relation weights are not tuned on rich entities only;
   - at least 4 of the 15 validation queries are in the sparse tier.

   The query grid (0021) weights its region and heritage-area cells towards the states and types that the
   audit shows as thin. If the sparse quota is still short after curation, backstories are written from audit
   entries that have an item and are in the corpus. This top-up is decided by tier alone, before any test run,
   and those queries are flagged in the query file.
4. **Results by tier.** The frozen analysis plan carries these as secondary hypotheses:
   - RQ1 and RQ3 per tier, with 95% bootstrap intervals;
   - the interaction test, rich against sparse;
   - the regression on the continuous score.

   They are kept apart from the primary Holm family, so the headline test keeps its power. LLM-versus-author
   agreement is also reported per tier, to check whether the judge is less reliable on entities it knows
   little about.
5. **Off-Wikidata probe (stretch).** About 100–150 documents with no Wikidata item. Sources: audit-sample
   monuments that have no item, public-domain gazetteers and ASI reports (Internet Archive, 0016), and Kannada
   Wikisource if that collector is accepted. The documents are marked unlinked and kept out of the headline,
   with about 10 queries aimed at them. Expected result: graph-only retrieval fails, and hybrid falls back to
   text.
6. **Freeze, do not edit.** The Wikidata state is the set of per-entity revisions in the frozen snapshot
   (`lastrevid`), with the fetch dates in the manifest. No items are added to or edited on Wikidata during the
   study. The audit's list of missing monuments (list entry, source, search trail) is published with the
   benchmark, once each list's licence has been checked. Adding those monuments to Wikidata is left until after
   the release.

The data card and a Limitations paragraph report the audit rates. Claims are scoped to heritage that Wikidata
describes as of the snapshot. The per-tier results show how far the claims stretch beyond it. New outputs: a
coverage-audit table and a results-by-coverage-tier table.

## Changes to the plan's version

- **Tier variable.** The tiers use Wikidata's own coverage (sitelinks and statements), not our graph degree,
  so they do not move when the graph build changes. Degree is reported as a covariate.
- **Interaction test and regression.** These test the confound itself; three separate per-tier tests do not.
- **Tier per query.** Each query's tier comes from the target entity the author marked during curation, with a
  "no entity" group. The tier is not inferred from judged documents, which depend on the pools.
- **Quotas beyond the test set.** The dev set gets a sparse quota (at least 8), so tuning does not favour rich
  entities. The validation set gets one too (at least 4), with kappa reported per tier, to check the judge's
  bias towards entities it knows.
- **Hindi belt in the audit.** About 100 entries come from the Hindi belt, so the audit measures both RQ3
  languages, not only Kannada.
- **Sampling frame.** Only official lists, not Wikipedia list pages. Every "no item" result needs a search
  trail, and 10% of matches are checked twice.
- **Snapshot.** The snapshot is the set of per-entity revisions already saved (0020). No dump is needed.

## Consequences

- Corpus: `asi_remainder_v2`, and the same rule on the ASI seed stratum for any new draw, collected with the
  week-3 neighbour run. Decision 0002 and 0015 rows say "article in English, Hindi or Kannada" from v2 on;
  corpus v1 numbers stay as reported.
- Snapshot: a sitelink-count fetch (`wbgetentities`, sitelinks only) for the document entities at the freeze.
  This is not a bulk download.
- Queries: a `target_entity` and `coverage_tier` column in the query file.
- `docs/plan/analysis_plan.md`: the tier hypotheses, written in before any test run.
- The author's time: confirming about 300 audit matches.
