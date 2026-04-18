/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), refresh: jest.fn() }),
  usePathname: () => "/dashboards/purchase-analytics",
}));

// Mock recharts (heavy lib)
jest.mock("recharts", () => {
  const React = require("react");
  const MockComponent = (name) => {
    const C = React.forwardRef(({ children, ...props }, ref) => (
      <div data-testid={`mock-${name}`} ref={ref} {...props}>{children}</div>
    ));
    C.displayName = name;
    return C;
  };
  return {
    ResponsiveContainer: MockComponent("ResponsiveContainer"),
    BarChart: MockComponent("BarChart"),
    Bar: MockComponent("Bar"),
    LineChart: MockComponent("LineChart"),
    Line: MockComponent("Line"),
    XAxis: MockComponent("XAxis"),
    YAxis: MockComponent("YAxis"),
    CartesianGrid: MockComponent("CartesianGrid"),
    Tooltip: MockComponent("Tooltip"),
    Legend: MockComponent("Legend"),
    Cell: MockComponent("Cell"),
    PieChart: MockComponent("PieChart"),
    Pie: MockComponent("Pie"),
  };
});

// Mock axios
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get: jest.fn(() => Promise.resolve({ data: {} })),
  post: jest.fn(() => Promise.resolve({ data: {} })),
    create: jest.fn(function () { return this; }),
    isCancel: jest.fn(() => false),
    interceptors: { response: { use: jest.fn() } },
  },
  get: jest.fn(() => Promise.resolve({ data: {} })),
  post: jest.fn(() => Promise.resolve({ data: {} })),
  isCancel: jest.fn(() => false),
}));

import PurchaseAnalyticsPage from "@/app/dashboards/purchase-analytics/page";

describe("Purchase Analytics Page", () => {
  it("renders without crashing", () => {
    render(<PurchaseAnalyticsPage />);
    expect(screen.getByText("Purchase & Cost Analytics")).toBeInTheDocument();
  });

  it("shows all three tabs", () => {
    render(<PurchaseAnalyticsPage />);
    expect(screen.getByText("Cost Trends")).toBeInTheDocument();
    expect(screen.getByText("Purchase vs. Sold")).toBeInTheDocument();
    expect(screen.getByText("Working Capital")).toBeInTheDocument();
  });

  it("shows page description", () => {
    render(<PurchaseAnalyticsPage />);
    expect(screen.getByText(/FOB cost tracking/)).toBeInTheDocument();
  });

  it("shows loading state initially", () => {
    render(<PurchaseAnalyticsPage />);
    expect(screen.getByText(/Loading cost trends/)).toBeInTheDocument();
  });
});
