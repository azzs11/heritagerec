import { afterEach, describe, expect, it, vi } from "vitest";

import { Refused, Unavailable, api, get, stepLabel } from "@/lib/api";

function answer(status: number, body: unknown) {
  return vi.fn().mockImplementation(
    async () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );
}

describe("the API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("turns a missing part into Unavailable with its reason and fix", async () => {
    vi.stubGlobal("fetch", answer(503, { detail: { part: "keyword", reason: "Java is not configured", fix: "set JAVA_HOME" } }));
    const e = (await api.search("fort", "bm25").catch((x) => x)) as Unavailable;
    expect(e).toBeInstanceOf(Unavailable);
    expect([e.part, e.reason, e.fix]).toEqual(["keyword", "Java is not configured", "set JAVA_HOME"]);
  });

  it("turns refused input into Refused with the server's words", async () => {
    vi.stubGlobal("fetch", answer(400, { detail: "the query is empty" }));
    const e = (await get("/api/search", { q: "" }).catch((x) => x)) as Refused;
    expect(e).toBeInstanceOf(Refused);
    expect(e.status).toBe(400);
    expect(e.message).toBe("the query is empty");
  });

  it("joins validation messages", async () => {
    vi.stubGlobal("fetch", answer(422, { detail: [{ msg: "lat too large" }, { msg: "lon missing" }] }));
    const e = (await get("/api/atlas/near").catch((x) => x)) as Refused;
    expect(e.message).toBe("lat too large; lon missing");
  });

  it("says how to start the server when nothing answers", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const e = (await api.health().catch((x) => x)) as Unavailable;
    expect(e).toBeInstanceOf(Unavailable);
    expect(e.fix).toContain("uv run python -m server");
  });

  it("encodes ids in paths and drops empty parameters", async () => {
    const f = answer(200, {});
    vi.stubGlobal("fetch", f);
    await api.ego("wikipedia:en:7051661#3", 150);
    await api.search("x", "bm25", undefined);
    expect(f.mock.calls[0]?.[0]).toContain("/api/graph/ego/wikipedia%3Aen%3A7051661%233?budget=150");
    expect(f.mock.calls[1]?.[0]).not.toContain("lang=");
  });
});

describe("path steps", () => {
  const fact = { source: "temple", target: "dynasty", relation: "P112", relation_label: "founded by", layer: "core", revision: "1" };
  it("read forward when walked from the fact's subject", () => {
    expect(stepLabel(fact, "temple")).toBe("founded by →");
  });
  it("read backward when walked from its object", () => {
    expect(stepLabel(fact, "dynasty")).toBe("← founded by");
  });
});
