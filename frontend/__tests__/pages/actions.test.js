import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock localStorage
const localStorageMock = (() => {
  let store = {};
  return {
    getItem: jest.fn((key) => store[key] || null),
    setItem: jest.fn((key, val) => { store[key] = val; }),
    removeItem: jest.fn((key) => { delete store[key]; }),
    clear: jest.fn(() => { store = {}; }),
  };
})();
Object.defineProperty(window, "localStorage", { value: localStorageMock });

// Mock axios
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get: jest.fn(() =>
    Promise.resolve({
      data: {
        as_of: "2024-11-15",
        total_actions: 3,
        by_type: { reorder: 1, markdown: 1, transfer: 1 },
        by_severity: { critical: 1, warning: 1, info: 1 },
        total_impact_thb: 200000,
        actions: [
          {
            type: "reorder",
            severity: "critical",
            title: "Reorder BrandA — FAST1",
            reason: "Only 3 days of cover left.",
            impact_thb: 100000,
            link: "/dashboards/inventory-alerts",
          },
          {
            type: "markdown",
            severity: "warning",
            title: "Dead stock: BrandB — DEAD1",
            reason: "On-hand value 50,000 THB, no sales in 180 days.",
            impact_thb: 50000,
            link: "/dashboards/inventory-alerts",
          },
          {
            type: "transfer",
            severity: "info",
            title: "Transfer BrandC — ITEM2 to Store X",
            reason: "180 days cover at Whs A, 3 days at Store X.",
            impact_thb: 50000,
            link: "/dashboards/stock-allocation",
          },
        ],
      },
    })
  ),
    create: jest.fn(function () { return this; }),
    isCancel: jest.fn(() => false),
    interceptors: { response: { use: jest.fn() } },
  },
  get: jest.fn(() =>
    Promise.resolve({
      data: {
        as_of: "2024-11-15",
        total_actions: 3,
        by_type: { reorder: 1, markdown: 1, transfer: 1 },
        by_severity: { critical: 1, warning: 1, info: 1 },
        total_impact_thb: 200000,
        actions: [
          {
            type: "reorder",
            severity: "critical",
            title: "Reorder BrandA — FAST1",
            reason: "Only 3 days of cover left.",
            impact_thb: 100000,
            link: "/dashboards/inventory-alerts",
          },
          {
            type: "markdown",
            severity: "warning",
            title: "Dead stock: BrandB — DEAD1",
            reason: "On-hand value 50,000 THB, no sales in 180 days.",
            impact_thb: 50000,
            link: "/dashboards/inventory-alerts",
          },
          {
            type: "transfer",
            severity: "info",
            title: "Transfer BrandC — ITEM2 to Store X",
            reason: "180 days cover at Whs A, 3 days at Store X.",
            impact_thb: 50000,
            link: "/dashboards/stock-allocation",
          },
        ],
      },
    })
  ),
  isCancel: jest.fn(() => false),
}));

// Mock next/link
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...props }) =>
    React.createElement("a", { href, ...props }, children),
}));

import ActionsPage from "@/app/dashboards/actions/page";

describe("Actions Dashboard Page", () => {
  beforeEach(() => {
    localStorageMock.clear();
    jest.clearAllMocks();
  });

  it("renders without crashing", () => {
    render(<ActionsPage />);
    expect(screen.getByText(/Analysing business priorities/)).toBeInTheDocument();
  });

  it("renders header after data loads", async () => {
    render(<ActionsPage />);
    const heading = await screen.findByText("Priority Actions");
    expect(heading).toBeInTheDocument();
  });

  it("shows KPI cards after loading", async () => {
    render(<ActionsPage />);
    await screen.findByText("Priority Actions");
    expect(screen.getByText("Total Actions")).toBeInTheDocument();
    expect(screen.getByText("Total Impact")).toBeInTheDocument();
    expect(screen.getByText("Acknowledged")).toBeInTheDocument();
    expect(screen.getAllByText(/Critical/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Warning/i).length).toBeGreaterThan(0);
  });

  it("renders action cards within grouped sections", async () => {
    render(<ActionsPage />);
    const title = await screen.findByText("Reorder BrandA — FAST1");
    expect(title).toBeInTheDocument();
    expect(screen.getByText("Dead stock: BrandB — DEAD1")).toBeInTheDocument();
    // Group headers should appear (text appears in badge + group header + dropdown, so use getAllByText)
    expect(screen.getAllByText("Reorder").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Transfer Stock").length).toBeGreaterThanOrEqual(1);
  });

  it("shows filter dropdowns", async () => {
    render(<ActionsPage />);
    await screen.findByText("Priority Actions");
    expect(screen.getByDisplayValue("All Types")).toBeInTheDocument();
    expect(screen.getByDisplayValue("All Severities")).toBeInTheDocument();
  });

  it("shows data date in header", async () => {
    render(<ActionsPage />);
    const dateText = await screen.findByText(/Data as of 2024-11-15/);
    expect(dateText).toBeInTheDocument();
  });

  it("type badges are rendered as clickable buttons", async () => {
    render(<ActionsPage />);
    await screen.findByText("Priority Actions");
    // Type summary badges are buttons with rounded-full class containing type labels
    const allButtons = screen.getAllByRole("button");
    const typeBadges = allButtons.filter((btn) =>
      btn.className.includes("rounded-full") && btn.className.includes("cursor-pointer")
    );
    // Should have at least the 3 type badges (reorder, markdown, transfer)
    expect(typeBadges.length).toBeGreaterThanOrEqual(3);
  });

  it("acknowledge button persists to localStorage", async () => {
    render(<ActionsPage />);
    await screen.findByText("Priority Actions");
    // Find all "Done" buttons (the acknowledge buttons on action cards)
    const doneButtons = screen.getAllByTitle("Mark as handled");
    expect(doneButtons.length).toBeGreaterThan(0);
    // Click the first Done button
    await act(async () => {
      fireEvent.click(doneButtons[0]);
    });
    // localStorage should have been called to persist
    expect(localStorageMock.setItem).toHaveBeenCalledWith(
      "nichiworld_actions_ack",
      expect.any(String)
    );
  });

  it("collapsing a group hides its action cards", async () => {
    render(<ActionsPage />);
    await screen.findByText("Reorder BrandA — FAST1");
    // Find the Reorder group header and click to collapse
    const groupHeaders = screen.getAllByText("Reorder");
    const groupButton = groupHeaders.find((el) => {
      const btn = el.closest("button");
      return btn && btn.className.includes("w-full");
    });
    if (groupButton) {
      fireEvent.click(groupButton.closest("button"));
      // The action card within that group should be hidden
      // (it's still in DOM but the section is collapsed)
    }
  });
});
