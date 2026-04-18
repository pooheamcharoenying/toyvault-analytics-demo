import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock axios
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get: jest.fn(() =>
      Promise.resolve({
        data: { locations: [], summary: {}, company_avg: {} },
      })
    ),
    create: jest.fn(function () { return this; }),
    isCancel: jest.fn(() => false),
    interceptors: { response: { use: jest.fn() } },
  },
  get: jest.fn(() =>
    Promise.resolve({
      data: { locations: [], summary: {}, company_avg: {} },
    })
  ),
  isCancel: jest.fn(() => false),
}));

// Mock recharts
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => React.createElement("div", null, children),
  BarChart: ({ children }) => React.createElement("div", null, children),
  Bar: () => null,
  LineChart: ({ children }) => React.createElement("div", null, children),
  Line: () => null,
  ScatterChart: ({ children }) => React.createElement("div", null, children),
  Scatter: () => null,
  XAxis: () => null,
  YAxis: () => null,
  ZAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  Cell: () => null,
}));

import LocationsListPage from "@/app/dashboards/locations/page";

describe("Locations List Page", () => {
  it("renders without crashing", () => {
    render(<LocationsListPage />);
    expect(document.body.querySelector("div")).toBeTruthy();
  });

  it("shows the page title", () => {
    render(<LocationsListPage />);
    // "Locations" appears in both breadcrumb and heading
    const matches = screen.getAllByText("Locations");
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("shows tab navigation", () => {
    render(<LocationsListPage />);
    expect(screen.getByText("Performance")).toBeInTheDocument();
    expect(screen.getByText("Investment Analysis")).toBeInTheDocument();
    expect(screen.getByText("Sales Trends")).toBeInTheDocument();
    expect(screen.getByText("Product Mix")).toBeInTheDocument();
  });

  it("shows price basis description", () => {
    render(<LocationsListPage />);
    expect(
      screen.getByText(/Revenue uses actual sales prices.*Master Price/i)
    ).toBeInTheDocument();
  });
});
