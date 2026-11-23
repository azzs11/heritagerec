import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const PAGES = ["/", "/atlas/", "/cases/", "/cases/?q=Hoysala%20temples%20Belur", "/graph/", "/graph/?node=Q668", "/ledger/", "/lab/", "/guide/", "/document/?id=wikipedia%3Aen%3A7051661"];

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  // The loading line ("Reading the corpus manifest…") must be gone; headings that begin with "Reading" are not it.
  await expect(page.getByText(/^Reading .*…$/)).toHaveCount(0);
}

// A 503 is the server saying a part is missing (no Java or no corpus, as in CI): the page shows why, which is
// expected behaviour, not an error. Every other console error still fails the test.
function realErrors(messages: string[]) {
  return messages.filter((m) => !/status of 503/.test(m));
}

async function corpusRunning(page: Page) {
  const h = await (await page.request.get("http://127.0.0.1:8000/api/health")).json();
  return h.corpus.status === "ok";
}

async function keywordRunning(page: Page) {
  const h = await (await page.request.get("http://127.0.0.1:8000/api/health")).json();
  return h.keyword.status === "ok" && h.corpus.status === "ok";
}

for (const path of PAGES) {
  test(`${path} loads cleanly, passes axe and fits the screen`, async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push(String(e)));
    // axe measures the settled page: with motion reduced, nothing is caught halfway through a fade.
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto(path);
    await settle(page);
    expect(realErrors(errors)).toEqual([]);
    const axe = await new AxeBuilder({ page }).analyze();
    const serious = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}

test("search reads the question twice and explains a result in a drawer that adds up", async ({ page }) => {
  test.skip(!(await keywordRunning(page)), "keyword search or the corpus is not running");
  await page.goto("/cases/?q=Hoysala%20temples%20Belur");
  await settle(page);
  const text = page.getByRole("list", { name: "Text lens results" });
  const graph = page.getByRole("list", { name: "Graph lens results" });
  await expect(text.getByRole("article").first()).toBeVisible();
  // The linker found the starting points by itself.
  await expect(page.getByRole("button", { name: "Remove Hoysala Empire" })).toBeVisible();
  await expect(graph.getByRole("article").first()).toBeVisible();
  await text.getByRole("button", { name: "Working" }).first().click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText(/^Adds up/)).toBeVisible();
  await expect(drawer.getByText(/^Does not add up/)).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
});

test("a document both lenses found is joined across the spine on hover", async ({ page }) => {
  test.skip(!(await keywordRunning(page)), "keyword search or the corpus is not running");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/cases/?q=Hoysala%20temples%20Belur");
  await settle(page);
  const both = page.locator("article", { hasText: "also graph" }).first();
  await expect(both).toBeVisible();
  const id = await both.getAttribute("data-doc");
  await both.hover();
  await expect(page.locator(`article[data-doc="${id}"]`)).toHaveCount(2);
  await expect(page.locator("svg path[class*='lineLit']")).toHaveCount(1);
});

test("unbuilt steps say so instead of showing anything", async ({ page }) => {
  test.skip(!(await keywordRunning(page)), "keyword search or the corpus is not running");
  await page.goto("/cases/?q=Mughal%20miniature%20painting");
  await settle(page);
  await expect(page.getByRole("button", { name: /Fusion\s*not built/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Verdict\s*not measured/ })).toBeVisible();
});

test("the slash key returns to the question", async ({ page }) => {
  test.skip(!(await keywordRunning(page)), "keyword search or the corpus is not running");
  await page.goto("/cases/?q=Hoysala%20temples%20Belur");
  await settle(page);
  await page.locator("body").click({ position: { x: 5, y: 400 } });
  await page.keyboard.press("/");
  await expect(page.getByRole("textbox", { name: "Question" })).toBeFocused();
});

test("a hub is folded, never drawn whole", async ({ page }) => {
  await page.goto("/graph/?node=Q668");
  await settle(page);
  await expect(page.getByText(/This node joins/)).toBeVisible();
  const text = await page.getByText(/nodes · .* bundles/).innerText();
  const [nodes, bundles] = (text.match(/[\d,]+/g) ?? []).map((n) => Number(n.replace(/,/g, "")));
  expect((nodes ?? 0) + (bundles ?? 0)).toBeLessThanOrEqual(400);
  await expect(page.getByText(/a hub opens one step/)).toBeVisible();
});

test("a neighbourhood opens two steps out and a path can be walked", async ({ page }) => {
  await page.goto("/graph/?node=Q466581");
  await settle(page);
  const text = await page.getByText(/nodes · .* bundles/).innerText();
  expect(Number(text.match(/\d+/)?.[0])).toBeGreaterThan(20); // the first ring alone holds 14
  await page.getByRole("button", { name: "Vijayanagara Empire" }).first().click();
  await page.getByRole("button", { name: "Walk the path" }).click();
  await expect(page.getByText("avoids hubs")).toBeVisible();
  await expect(page.getByRole("button", { name: "clear the path" })).toBeVisible();
});

test("the overview draws the connected communities and shelves the rest", async ({ page }) => {
  await page.goto("/graph/");
  await settle(page);
  const shelf = page.getByRole("list").filter({ has: page.getByRole("button", { name: /Mallabhum/ }) });
  await expect(shelf).toBeVisible();
  await shelf.getByRole("button", { name: /Mallabhum/ }).click();
  await expect(page.getByText("its most connected members")).toBeVisible();
});

test("the atlas answers what is near Belur, and its filters work", async ({ page }) => {
  await page.goto("/atlas/?lat=13.16&lon=75.87");
  await settle(page);
  await expect(page.getByRole("heading", { name: /places within/ })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Places near the chosen point" }).getByRole("link", { name: /Belur/ }).first()).toBeVisible();
  const kinds = page.getByRole("list", { name: /Kinds of place/ });
  const sites = kinds.getByRole("button", { name: /sites and places/ });
  await sites.click();
  await expect(sites).toHaveAttribute("aria-pressed", "false");
  // The period panel is left off phones, where the map has no room beside it.
  if ((page.viewportSize()?.width ?? 0) >= 768) {
    const latest = page.getByRole("slider", { name: "Latest century" });
    await latest.fill("15");
    await expect(page.getByText(/– 15th c\./)).toBeVisible();
  }
});

test("the masthead finder offers a search and the entities it knows", async ({ page }) => {
  await page.goto("/guide/");
  await settle(page);
  await page.keyboard.press("/");
  const box = page.getByRole("combobox", { name: /Search the archive/ });
  await expect(box).toBeFocused();
  await box.fill("Hampi");
  const options = page.getByRole("option");
  await expect(options.first()).toContainText("Search for");
  await expect(options.filter({ hasText: "Hampi" }).nth(1)).toBeVisible();
  await box.press("Enter");
  await expect(page).toHaveURL(/\/cases\/\?q=Hampi/);
});

test("a refused query says why", async ({ page }) => {
  test.skip(!(await keywordRunning(page)), "keyword search or the corpus is not running");
  await page.goto("/cases/?q=%3A");
  await settle(page);
  await expect(page.getByText(/no searchable words/)).toBeVisible();
});

test("chosen starting points rank documents and each chain reads the right way", async ({ page }) => {
  test.skip(!(await keywordRunning(page)), "keyword search or the corpus is not running");
  await page.goto("/cases/?q=Hoysala%20temples%20Belur&seeds=Q466581");
  await settle(page);
  const graph = page.getByRole("list", { name: "Graph lens results" });
  await expect(graph.getByRole("article").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "use the linked names" })).toBeVisible();
  // Documents point to their entity ("document is about"), so walking from the entity reads it backward.
  await expect(graph.getByText("← document is about").first()).toBeVisible();
  await expect(graph.getByText("document is about →")).toHaveCount(0);
});

// ---------- dead ends, downloads, flow ----------

test("a question the archive cannot answer says so and offers other ways", async ({ page }) => {
  test.skip(!(await keywordRunning(page)), "keyword search or the corpus is not running");
  await page.goto("/cases/?q=xqzv%20blorp");
  await settle(page);
  await expect(page.getByRole("heading", { name: /has not been written here/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Wikipedia \(English\)/ })).toHaveAttribute("href", /en\.wikipedia\.org.*search=xqzv/);
  await expect(page.getByRole("link", { name: "Walk the atlas" })).toBeVisible();
});

test("a partial match is flagged, and a misspelling is rescued by the graph", async ({ page }) => {
  test.skip(!(await keywordRunning(page)), "keyword search or the corpus is not running");
  await page.goto("/cases/?q=colosseum%20gladiators%20rome");
  await settle(page);
  await expect(page.getByRole("heading", { name: /answer only part of the question/ })).toBeVisible();
  await page.goto("/cases/?q=hoysla%20tempels");
  await settle(page);
  await expect(page.getByRole("heading", { name: /graph found a way in/ })).toBeVisible();
  await expect(page.getByRole("list", { name: "Graph lens results" }).getByRole("article").first()).toBeVisible();
});

test("a document can be taken away with its licence written in", async ({ page }) => {
  test.skip(!(await keywordRunning(page)), "the corpus is not running");
  await page.goto("/document/?id=wikipedia%3Aen%3A7051661");
  await settle(page);
  const txt = page.getByRole("link", { name: /^Text/ });
  const href = await txt.getAttribute("href");
  const body = await (await page.request.get(href!)).text();
  expect(body).toContain("licence: https://creativecommons.org/licenses/by-sa/4.0/");
  await expect(page.getByRole("link", { name: /PDF from Wikipedia/ })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "From here" }).getByRole("link", { name: /More like this/ })).toBeVisible();
});

test("an address that does not exist is answered, not left blank", async ({ page }) => {
  await page.goto("/no-such-page/");
  await expect(page.getByRole("heading", { name: "This page is not in the archive." })).toBeVisible();
  if (await corpusRunning(page)) {
    await page.goto("/document/?id=nope");
    await settle(page);
    await expect(page.getByRole("heading", { name: "Not in the archive." })).toBeVisible();
  }
});

test("the reader's path is drawn as they move, and the sky stays off the map", async ({ page }) => {
  await page.goto("/graph/?node=Q466581");
  await settle(page);
  await page.goto("/atlas/?lat=13.16&lon=75.87");
  await settle(page);
  const trail = page.getByRole("navigation", { name: "Your path through the archive" });
  await expect(trail.getByRole("link")).toHaveCount(2);
  await expect(page.locator(".sky")).toHaveCount(0);
  await page.goto("/guide/");
  await expect(page.locator(".sky")).toHaveCount(1);
});

// ---------- hexagons (decision 0030) ----------

test("the atlas drawer counts the neighbourhood ring by ring", async ({ page }) => {
  await page.goto("/atlas/?lat=13.16&lon=75.87");
  await settle(page);
  const drawer = page.getByRole("complementary", { name: "Places near the chosen point" });
  await expect(drawer.getByText("Ring by ring")).toBeVisible({ timeout: 15_000 });
  await expect(drawer.getByText("same hexagon")).toBeVisible();
  await expect(drawer.getByText("1 ring out")).toBeVisible();
});

test("a document recommends nearby documents ring by ring", async ({ page }) => {
  test.skip(!(await corpusRunning(page)), "needs the corpus");
  await page.goto("/document/?id=wikipedia%3Aen%3A7051661");
  await settle(page);
  await expect(page.getByText("Nearby, ring by ring")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("2 rings out")).toBeVisible();
});

// ---------- screenshots: pages whose look should not change unnoticed (local only: fonts differ on CI's Linux) ----------

test.describe("screenshots", () => {
  test.skip(!!process.env.CI, "baselines are drawn on macOS; Linux renders text differently");
  for (const [name, path] of [
    ["guide", "/guide/"],
    ["not-found", "/no-such-page/"],
  ] as const) {
    test(`${name} looks as recorded`, async ({ page }) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.addInitScript(() => {
        try {
          sessionStorage.clear();
          localStorage.setItem("guide-offered", "yes");
        } catch {}
      });
      await page.goto(path);
      await settle(page);
      // The sky drifts (decoration), and Next's development badge is not part of the site.
      await page.addStyleTag({ content: ".sky,nextjs-portal{display:none!important}" });
      await expect(page).toHaveScreenshot(`${name}.png`, { fullPage: true, maxDiffPixelRatio: 0.01 });
    });
  }
});
