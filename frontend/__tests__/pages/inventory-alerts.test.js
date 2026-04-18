import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/dashboards/inventory-alerts",
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
}));

// Mock axios
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get: jest.fn(() => Promise.resolve({ data: { rows: [], summary: {} } })),
    create: jest.fn(function () { return this; }),
    isCancel: jest.fn(() => false),
    interceptors: { response: { use: jest.fn() } },
  },
  get: jest.fn(() => Promise.resolve({ data: { rows: [], summary: {} } })),
  isCancel: jest.fn(() => false),
}));

// Mock recharts
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => React.createElement("div", { "data-testid": "chart-container" }, children),
  BarChart: ({ children }) => React.createElement("div", null, children),
  Bar: () => null,
  PieChart: ({ children }) => React.createElement("div", null, children),
  Pie: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Cell: () => null,
}));

import InventoryAlertsPage from "@/app/dashboards/inventory-alerts/page";

describe("Inventory Alerts Page", () => {
  it("renders without crashing", () => {
    render(<InventoryAlertsPage />);
    expect(screen.getByText("Inventory Action Alerts")).toBeInTheDocument();
  });

  it("shows all three tabs", () => {
    render(<InventoryAlertsPage />);
    expect(screen.getByText("Stockout Risk")).toBeInTheDocument();
    expect(screen.getByText("Dead Stock")).toBeInTheDocument();
    expect(screen.getByText("Reorder Analysis")).toBeInTheDocument();
  });

  it("shows Stockout Risk tab content by default", () => {
    render(<InventoryAlertsPage />);
    expect(screen.getByText(/Loading stockout risk/)).toBeInTheDocument();
  });

  it("has brand filter input and apply button", () => {
    render(<InventoryAlertsPage />);
    expect(screen.getByPlaceholderText("Filter by brand name...")).toBeInTheDocument();
    expect(screen.getByText("Apply")).toBeInTheDocument();
  });
});
