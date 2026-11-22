import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const PAGES = ["/", "/atlas/", "/cases/?q=Hoysala%20temples%20Belur", "/graph/", "/graph/?node=Q668", "/ledger/", "/lab/", "/guide/", "/document/?id=wikipedia%3Aen%3A7051661"];

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

test("a case explains its first result, and the explanation adds up", async ({ page }) => {
  test.skip(!(await keywordRunning(page)), "keyword search or the corpus is not running");
  await page.goto("/cases/?q=Hoysala%20temples%20Belur");
  await settle(page);
  await expect(page.getByRole("region", { name: "Text lens" }).getByRole("listitem").first()).toBeVisible();
  await page.getByRole("button", { name: /why here/ }).first().click();
  await expect(page.getByText("adds up", { exact: true })).toBeVisible();
  await expect(page.getByText("does not add up")).toHaveCount(0);
});

test("unbuilt systems say so instead of showing anything", async ({ page }) => {
  test.skip(!(await keywordRunning(page)), "keyword search or the corpus is not running");
  await page.goto("/cases/?q=Mughal%20miniature%20painting");
  await settle(page);
  // The graph ranking exists; what is missing is the linker, and the lens says so.
  await expect(page.getByRole("region", { name: "Graph lens" }).getByText("linker not built")).toBeVisible();
  await expect(page.getByText("not built yet").first()).toBeVisible(); // fusion, reranker, LambdaMART
  await expect(page.getByText("not measured yet")).toBeVisible();
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

test("the graph lens ranks documents from chosen entities and reads each path the right way", async ({ page }) => {
  test.skip(!(await keywordRunning(page)), "keyword search or the corpus is not running");
  await page.goto("/cases/?q=Hoysala%20temples%20Belur&seeds=Q466581");
  await settle(page);
  const lens = page.getByRole("region", { name: "Graph lens" });
  await expect(lens.getByRole("listitem").filter({ hasText: "Hoysala" }).first()).toBeVisible();
  // Documents point to their entity ("document is about"), so walking from the entity reads it backward.
  await expect(lens.getByText("← document is about").first()).toBeVisible();
  await expect(lens.getByText("document is about →")).toHaveCount(0);
});
