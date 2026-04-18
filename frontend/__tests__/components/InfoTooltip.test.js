import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import InfoTooltip, { METRIC_TOOLTIPS } from "@/components/InfoTooltip";

describe("InfoTooltip", () => {
  it("renders the info icon button", () => {
    render(<InfoTooltip text="Test tooltip text" />);
    const btn = screen.getByRole("button", { name: /more info/i });
    expect(btn).toBeInTheDocument();
  });

  it("shows tooltip text on click", () => {
    render(<InfoTooltip text="Explanation of this metric" />);
    const btn = screen.getByRole("button", { name: /more info/i });
    fireEvent.click(btn);
    expect(screen.getByText("Explanation of this metric")).toBeInTheDocument();
  });

  it("hides tooltip on second click", () => {
    render(<InfoTooltip text="Toggle me" />);
    const btn = screen.getByRole("button", { name: /more info/i });
    fireEvent.click(btn);
    expect(screen.getByText("Toggle me")).toBeInTheDocument();
    fireEvent.click(btn);
    expect(screen.queryByText("Toggle me")).not.toBeInTheDocument();
  });

  it("renders with size='md' without crashing", () => {
    render(<InfoTooltip text="Medium size tooltip" size="md" />);
    expect(screen.getByRole("button", { name: /more info/i })).toBeInTheDocument();
  });

  it("renders with size='sm' (default) without crashing", () => {
    render(<InfoTooltip text="Small tooltip" />);
    expect(screen.getByRole("button", { name: /more info/i })).toBeInTheDocument();
  });
});

describe("METRIC_TOOLTIPS", () => {
  it("has tooltip entries for all major dashboard categories", () => {
    expect(METRIC_TOOLTIPS.executive).toBeDefined();
    expect(METRIC_TOOLTIPS.inventory).toBeDefined();
    expect(METRIC_TOOLTIPS.allocation).toBeDefined();
    expect(METRIC_TOOLTIPS.location).toBeDefined();
    expect(METRIC_TOOLTIPS.product).toBeDefined();
    expect(METRIC_TOOLTIPS.purchase).toBeDefined();
    expect(METRIC_TOOLTIPS.seasonality).toBeDefined();
    expect(METRIC_TOOLTIPS.period).toBeDefined();
    expect(METRIC_TOOLTIPS.actions).toBeDefined();
    expect(METRIC_TOOLTIPS.stores).toBeDefined();
    expect(METRIC_TOOLTIPS.item).toBeDefined();
  });

  it("executive tooltips are non-empty strings", () => {
    Object.values(METRIC_TOOLTIPS.executive).forEach((tip) => {
      expect(typeof tip).toBe("string");
      expect(tip.length).toBeGreaterThan(10);
    });
  });

  it("inventory tooltips include key metrics", () => {
    expect(METRIC_TOOLTIPS.inventory.days_of_cover).toContain("daily sales");
    expect(METRIC_TOOLTIPS.inventory.sell_through_rate).toContain("sold");
    expect(METRIC_TOOLTIPS.inventory.projected_stockout).toContain("run out of stock");
    expect(METRIC_TOOLTIPS.inventory.suggested_reorder_qty).toContain("order");
  });

  it("location tooltips explain the health score weighting", () => {
    expect(METRIC_TOOLTIPS.location.health_score).toContain("40%");
    expect(METRIC_TOOLTIPS.location.health_score).toContain("25%");
  });

  it("product tooltips explain ABC classification", () => {
    expect(METRIC_TOOLTIPS.product.abc_class).toContain("80%");
    expect(METRIC_TOOLTIPS.product.abc_class).toContain("A-class");
  });
});
