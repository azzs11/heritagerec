import type { Portrait as Data } from "@/lib/api";

import s from "./Portrait.module.css";

/**
 * A document's data portrait (decision 0034): where it is and when, drawn from recorded facts only, for documents
 * with no photograph. The top is a locator on India's graticule (no borders: the atlas draws none, decision 0025);
 * the strip below is the timeline from the 25th century BCE to now, the document's centuries marked. A missing fact
 * is drawn as unknown, never guessed. The script mark keeps the document's language in view.
 */
const BOX = { west: 66, east: 98, south: 6, north: 37 };
const FIRST = -25;
const LAST = 21;
const SCRIPT: Record<string, string> = { en: "En", hi: "हि", kn: "ಕ" };

const x = (lon: number) => 4 + ((lon - BOX.west) / (BOX.east - BOX.west)) * 56;
const y = (lat: number) => 4 + 40 - ((lat - BOX.south) / (BOX.north - BOX.south)) * 40;
const t = (c: number) => 4 + ((c - FIRST) / (LAST - FIRST)) * 56;

function ordinal(n: number): string {
  const teen = n % 100 >= 11 && n % 100 <= 13;
  const suffix = teen ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}

export function centuryText(cs: number[]): string {
  if (!cs.length) return "no recorded century";
  const name = (c: number) => (c < 0 ? `${ordinal(-c)} century BCE` : `${ordinal(c)} century`);
  const first = cs[0]!;
  const last = cs[cs.length - 1]!;
  return first === last ? name(first) : `${name(first)} to ${name(last)}`;
}

export function Portrait({ data, language, label }: { data?: Data; language: string; label?: string }) {
  const placed = data?.lat != null && data.lon != null;
  const cs = data?.centuries ?? [];
  const where = placed ? "a recorded place" : "no recorded place";
  return (
    <svg className={s.portrait} viewBox="0 0 64 64" role="img" aria-label={label ?? `${where}; ${centuryText(cs)}`}>
      <title>{`${where}; ${centuryText(cs)}`}</title>
      {[70, 80, 90].map((lon) => (
        <line key={lon} className={s.grid} x1={x(lon)} y1={4} x2={x(lon)} y2={44} />
      ))}
      {[10, 20, 30].map((lat) => (
        <line key={lat} className={s.grid} x1={4} y1={y(lat)} x2={60} y2={y(lat)} />
      ))}
      {placed ? (
        <>
          <circle className={s.halo} cx={x(data!.lon!)} cy={y(data!.lat!)} r={5} />
          <circle className={s.dot} cx={x(data!.lon!)} cy={y(data!.lat!)} r={2.2} />
        </>
      ) : (
        <text className={s.unknown} x={32} y={28} textAnchor="middle">
          ?
        </text>
      )}
      <line className={s.axis} x1={4} y1={54} x2={60} y2={54} />
      <line className={s.zero} x1={t(0)} y1={51.5} x2={t(0)} y2={56.5} />
      {cs.map((c) => (
        <rect key={c} className={s.century} x={t(c) - 0.6} y={50} width={1.4} height={8} />
      ))}
      <text className={s.script} x={5} y={12} lang={language}>
        {SCRIPT[language] ?? language}
      </text>
    </svg>
  );
}
