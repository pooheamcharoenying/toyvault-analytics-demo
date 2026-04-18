import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useParams: jest.fn(() => ({ location: "TestWarehouse" })),
  useRouter: jest.fn(() => ({ back: jest.fn(), push: jest.fn() })),
  usePathname: jest.fn(() => "/dashboards/locations/TestWarehouse"),
  useSearchParams: jest.fn(() => new URLSearchParams()),
}));

// Mock axios
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get: jest.fn(() =>
      Promise.resolve({
        data: {
          location: "TestWarehouse",
          top_brands: [{ brand: "BrandX", sold_thb: 1000, sold_qty: 10 }],
          top_items: [],
          non_movers: [],
          non_mover_total_thb: 0,
          brand_heatmap: [],
        },
      })
    ),
    create: jest.fn(function () { return this; }),
    isCancel: jest.fn(() => false),
    interceptors: { response: { use: jest.fn() } },
  },
  isCancel: jest.fn(() => false),
}));

// Mock recharts
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => React.createElement("div", null, children),
  BarChart: ({ children }) => React.createElement("div", null, children),
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
}));

import LocationDetailPage from "@/app/dashboards/locations/[location]/page";

describe("Location Detail Page", () => {
  it("renders without crashing", () => {
    render(<LocationDetailPage />);
    expect(document.body.querySelector("div")).toBeTruthy();
  });

  it("shows the location name from URL param", () => {
    render(<LocationDetailPage />);
    expect(screen.getAllByText("TestWarehouse").length).toBeGreaterThanOrEqual(1);
  });

  it("shows breadcrumb with link to locations list", () => {
    render(<LocationDetailPage />);
    expect(screen.getByText("Locations")).toBeInTheDocument();
  });

  it("shows price basis in description", () => {
    render(<LocationDetailPage />);
    expect(
      screen.getByText(/Revenue uses actual sales.*Master Price/i)
    ).toBeInTheDocument();
  });
});
