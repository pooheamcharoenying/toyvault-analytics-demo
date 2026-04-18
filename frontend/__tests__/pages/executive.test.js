import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock axios
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get: jest.fn(() => Promise.resolve({ data: {} })),
    create: jest.fn(function () { return this; }),
    isCancel: jest.fn(() => false),
    interceptors: { response: { use: jest.fn() } },
  },
  get: jest.fn(() => Promise.resolve({ data: {} })),
  isCancel: jest.fn(() => false),
}));

// Mock recharts — render children as plain divs
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => React.createElement("div", { "data-testid": "chart-container" }, children),
  LineChart: ({ children }) => React.createElement("div", null, children),
  Line: () => null,
  BarChart: ({ children }) => React.createElement("div", null, children),
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Cell: () => null,
}));

import ExecutiveDashboard from "@/app/dashboards/executive/page";

describe("Executive Dashboard Page", () => {
  it("renders without crashing", () => {
    render(<ExecutiveDashboard />);
    // Should show the tab navigation
    expect(screen.getByText("Overview")).toBeInTheDocument();
  });

  it("shows all dashboard tabs", () => {
    render(<ExecutiveDashboard />);
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Trends")).toBeInTheDocument();
    expect(screen.getByText("Concentration")).toBeInTheDocument();
    expect(screen.getByText("Channels")).toBeInTheDocument();
    expect(screen.getByText("More")).toBeInTheDocument();
  });
});
