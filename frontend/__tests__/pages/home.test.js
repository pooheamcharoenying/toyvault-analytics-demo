import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/link
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...props }) =>
    React.createElement("a", { href, ...props }, children),
}));

import Home from "@/app/page";

describe("Home Page", () => {
  it("renders without crashing", () => {
    render(<Home />);
    expect(screen.getByText("Analytics")).toBeInTheDocument();
  });

  it("displays section headings", () => {
    render(<Home />);
    expect(screen.getByText("Core")).toBeInTheDocument();
    expect(screen.getByText("Inventory & Stock")).toBeInTheDocument();
    expect(screen.getByText("Products & Locations")).toBeInTheDocument();
    expect(screen.getByText("Analysis & Tools")).toBeInTheDocument();
  });

  it("displays all dashboard cards", () => {
    render(<Home />);
    expect(screen.getByText("Executive Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Operations")).toBeInTheDocument();
    expect(screen.getByText("Period Comparison")).toBeInTheDocument();
    expect(screen.getByText("Inventory Alerts")).toBeInTheDocument();
    expect(screen.getByText("Stock Allocation")).toBeInTheDocument();
    expect(screen.getByText("Purchase Analytics")).toBeInTheDocument();
    expect(screen.getByText("Brands & Products")).toBeInTheDocument();
    expect(screen.getByText("Locations & Stores")).toBeInTheDocument();
    expect(screen.getByText("Seasonality & Margin")).toBeInTheDocument();
    expect(screen.getByText("Barcode Lookup")).toBeInTheDocument();
  });

  it("cards link to correct pages", () => {
    render(<Home />);
    const links = screen.getAllByRole("link");
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/dashboards/executive");
    expect(hrefs).toContain("/task2");
    expect(hrefs).toContain("/dashboards/period-comparison");
    expect(hrefs).toContain("/dashboards/inventory-alerts");
    expect(hrefs).toContain("/dashboards/stock-allocation");
    expect(hrefs).toContain("/dashboards/purchase-analytics");
    expect(hrefs).toContain("/dashboards/brands");
    expect(hrefs).toContain("/dashboards/locations");
    expect(hrefs).toContain("/dashboards/seasonality-margin");
    expect(hrefs).toContain("/task1");
  });
});
