import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const PAGES = ["/", "/atlas/", "/cases/", "/cases/?q=Hoysala%20temples%20Belur", "/graph/", "/graph/?node=Q668", "/ledger/", "/lab/", "/guide/", "/document/?id=wikipedia%3Aen%3A7051661"];

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  // The loading line ("Reading the corpus manifest…") must be gone; headings that begin with "Reading" are not it.
  await expect(page.getByText(/^Reading .*…$/)).toHaveCount(0);
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
    await page.goto(path);
    await settle(page);
    expect(errors).toEqual([]);
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
  const text = await page.getByText(/nodes and .* bundles on screen/).innerText();
  const [nodes, bundles] = (text.match(/[\d,]+/g) ?? []).map((n) => Number(n.replace(/,/g, "")));
  expect((nodes ?? 0) + (bundles ?? 0)).toBeLessThanOrEqual(400);
});

test("the atlas answers what is near Belur", async ({ page }) => {
  await page.goto("/atlas/?lat=13.16&lon=75.87");
  await settle(page);
  await expect(page.getByRole("heading", { name: /nearest places/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Belur/ }).first()).toBeVisible();
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
