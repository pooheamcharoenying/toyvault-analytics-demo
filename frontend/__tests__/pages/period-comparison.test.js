/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), refresh: jest.fn() }),
  usePathname: () => "/dashboards/period-comparison",
}));

// Mock recharts
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

import PeriodComparisonPage from "@/app/dashboards/period-comparison/page";

describe("Period Comparison Page", () => {
  it("renders without crashing", () => {
    render(<PeriodComparisonPage />);
    expect(screen.getByText("Period Comparison")).toBeInTheDocument();
  });

  it("shows period selectors", () => {
    render(<PeriodComparisonPage />);
    expect(screen.getByText("Period A")).toBeInTheDocument();
    expect(screen.getByText("Period B")).toBeInTheDocument();
  });

  it("shows loading state initially (tabs hidden until data loads)", () => {
    render(<PeriodComparisonPage />);
    expect(screen.getByText("Loading comparison...")).toBeInTheDocument();
    // Tabs are only rendered after data loads, so they won't be present yet
    expect(screen.queryByText("Overview")).not.toBeInTheDocument();
  });
});
