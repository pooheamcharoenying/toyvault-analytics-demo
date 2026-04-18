/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), refresh: jest.fn() }),
  usePathname: () => "/dashboards/seasonality-margin",
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
    ComposedChart: MockComponent("ComposedChart"),
    Area: MockComponent("Area"),
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

import SeasonalityMarginPage from "@/app/dashboards/seasonality-margin/page";

describe("Seasonality & Margin Page", () => {
  it("renders without crashing", () => {
    render(<SeasonalityMarginPage />);
    expect(screen.getByText("Seasonality & Margin Analysis")).toBeInTheDocument();
  });

  it("shows both tabs", () => {
    render(<SeasonalityMarginPage />);
    expect(screen.getByText("Seasonality")).toBeInTheDocument();
    expect(screen.getByText("Margin Mix")).toBeInTheDocument();
  });

  it("shows page description", () => {
    render(<SeasonalityMarginPage />);
    expect(screen.getByText(/Monthly sales patterns/)).toBeInTheDocument();
  });

  it("shows loading state initially", () => {
    render(<SeasonalityMarginPage />);
    expect(screen.getByText(/Loading seasonality/)).toBeInTheDocument();
  });
});
