import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import AbcdeBadge, { ABCDE_SORT_VALUE } from "@/components/AbcdeBadge";

describe("AbcdeBadge", () => {
  it("renders the tier letter for each valid class", () => {
    const tiers = ["A", "B", "C", "D", "E"];
    tiers.forEach((tier) => {
      const { unmount } = render(<AbcdeBadge tier={tier} />);
      expect(screen.getByText(tier)).toBeInTheDocument();
      unmount();
    });
  });

  it("renders a dash for null or undefined tier", () => {
    const { container } = render(<AbcdeBadge tier={null} />);
    expect(container.textContent).toContain("—");
  });

  it("handles lowercase tier input", () => {
    render(<AbcdeBadge tier="a" />);
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("includes context in the title attribute", () => {
    render(<AbcdeBadge tier="B" context="by company revenue" />);
    const badge = screen.getByText("B");
    expect(badge.getAttribute("title")).toContain("by company revenue");
  });

  it("shows green styling for A tier", () => {
    render(<AbcdeBadge tier="A" />);
    const badge = screen.getByText("A");
    expect(badge.className).toContain("green");
  });

  it("shows red styling for E tier", () => {
    render(<AbcdeBadge tier="E" />);
    const badge = screen.getByText("E");
    expect(badge.className).toContain("red");
  });
});

describe("ABCDE_SORT_VALUE", () => {
  it("has numeric sort values for A through E", () => {
    expect(ABCDE_SORT_VALUE.A).toBe(1);
    expect(ABCDE_SORT_VALUE.B).toBe(2);
    expect(ABCDE_SORT_VALUE.C).toBe(3);
    expect(ABCDE_SORT_VALUE.D).toBe(4);
    expect(ABCDE_SORT_VALUE.E).toBe(5);
  });

  it("sorts A before E", () => {
    expect(ABCDE_SORT_VALUE.A).toBeLessThan(ABCDE_SORT_VALUE.E);
  });
});
