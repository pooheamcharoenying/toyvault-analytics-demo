import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock axios
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get: jest.fn(() => Promise.resolve({ data: { rows: [] } })),
    create: jest.fn(function () { return this; }),
    isCancel: jest.fn(() => false),
    interceptors: { response: { use: jest.fn() } },
  },
  get: jest.fn(() => Promise.resolve({ data: { rows: [] } })),
  isCancel: jest.fn(() => false),
}));

// Mock recharts
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => React.createElement("div", null, children),
  BarChart: ({ children }) => React.createElement("div", null, children),
  Bar: () => null,
  LineChart: ({ children }) => React.createElement("div", null, children),
  Line: () => null,
  PieChart: ({ children }) => React.createElement("div", null, children),
  Pie: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  Cell: () => null,
}));

import BrandsListPage from "@/app/dashboards/brands/page";

describe("Brands List Page", () => {
  it("renders without crashing", () => {
    render(<BrandsListPage />);
    expect(document.body.querySelector("div")).toBeTruthy();
  });

  it("shows the page title", () => {
    render(<BrandsListPage />);
    expect(screen.getByText("Brands & Products")).toBeInTheDocument();
  });

  it("shows tab navigation", () => {
    render(<BrandsListPage />);
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Product Classification")).toBeInTheDocument();
  });

  it("shows breadcrumb navigation", () => {
    render(<BrandsListPage />);
    expect(screen.getByText("Brands")).toBeInTheDocument();
  });
});
