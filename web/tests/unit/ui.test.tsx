import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Evidence, Names, fmt } from "@/components/ui";

describe("shared components", () => {
  it("sets every script a name has, each with its language", () => {
    const { container } = render(<Names labels={{ en: "Hampi", hi: "हम्पी", kn: "ಹಂಪೆ" }} fallback="Q1" />);
    expect([...container.querySelectorAll("[lang]")].map((e) => e.getAttribute("lang"))).toEqual(["en", "hi", "kn"]);
  });

  it("falls back to the id when no name exists", () => {
    const { container } = render(<Names labels={{}} fallback="Q42" />);
    expect(container.textContent).toBe("Q42");
  });

  it("marks only the matched words", () => {
    const { container } = render(
      <Evidence words={[{ word: "Belur", match: true }, { word: "is", match: false }, { word: "temples", match: true }]} />,
    );
    expect([...container.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["Belur", "temples"]);
  });

  it("formats numbers the Indian way", () => {
    expect(fmt(1234567)).toBe("12,34,567");
  });
});
