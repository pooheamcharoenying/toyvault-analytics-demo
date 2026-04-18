import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/dashboards/stock-allocation",
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
}));

// Mock axios
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get: jest.fn(() => Promise.resolve({ data: { summary: {}, recommendations: [], overstocked: [], understocked: [] } })),
    create: jest.fn(function () { return this; }),
    isCancel: jest.fn(() => false),
    interceptors: { response: { use: jest.fn() } },
  },
  get: jest.fn(() => Promise.resolve({ data: { summary: {}, recommendations: [], overstocked: [], understocked: [] } })),
  isCancel: jest.fn(() => false),
}));

// Mock recharts
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => React.createElement("div", { "data-testid": "chart-container" }, children),
  BarChart: ({ children }) => React.createElement("div", null, children),
  Bar: () => null,
  LineChart: ({ children }) => React.createElement("div", null, children),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  Cell: () => null,
}));

import StockAllocationPage from "@/app/dashboards/stock-allocation/page";

describe("Stock Allocation Page", () => {
  it("renders without crashing", () => {
    render(<StockAllocationPage />);
    expect(screen.getByText("Stock Allocation Optimization")).toBeInTheDocument();
  });

  it("shows all three tabs", () => {
    render(<StockAllocationPage />);
    expect(screen.getByText("Stock Allocation")).toBeInTheDocument();
    expect(screen.getByText("Transfer History")).toBeInTheDocument();
    expect(screen.getByText("Rebalancing Summary")).toBeInTheDocument();
  });

  it("shows page description", () => {
    render(<StockAllocationPage />);
    expect(screen.getByText(/overstocked and understocked/)).toBeInTheDocument();
  });

  it("shows brand filter on allocation tab", () => {
    render(<StockAllocationPage />);
    expect(screen.getByPlaceholderText(/Filter by brand/)).toBeInTheDocument();
  });
});
