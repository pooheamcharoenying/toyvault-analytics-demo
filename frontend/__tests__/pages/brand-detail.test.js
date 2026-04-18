import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useParams: jest.fn(() => ({ brand: "TestBrand" })),
  useRouter: jest.fn(() => ({ back: jest.fn(), push: jest.fn() })),
  usePathname: jest.fn(() => "/dashboards/brands/TestBrand"),
  useSearchParams: jest.fn(() => new URLSearchParams()),
}));

// Mock axios
jest.mock("axios", () => {
  const splitData = JSON.stringify({
    columns: ["ItemCode", "Description", "Brought_QTY", "Sold_QTY", "OnHand_QTY",
      "FOB_Price_THB", "Master_Price", "Total_Revenue_THB", "Total_Cost_THB",
      "Profit_Loss_THB", "Profit_Margin_%"],
    index: [0],
    data: [["IT001", "Test Item", 10, 5, 5, 100, 200, 1000, 500, 500, 50]],
  });
  return {
    __esModule: true,
    default: {
      get: jest.fn(() => Promise.resolve({ data: splitData })),
      create: jest.fn(function () { return this; }),
      isCancel: jest.fn(() => false),
      interceptors: { response: { use: jest.fn() } },
    },
    get: jest.fn(() => Promise.resolve({ data: splitData })),
    isCancel: jest.fn(() => false),
  };
});

// Mock recharts
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => React.createElement("div", null, children),
  BarChart: ({ children }) => React.createElement("div", null, children),
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
}));

import BrandDetailPage from "@/app/dashboards/brands/[brand]/page";

describe("Brand Detail Page", () => {
  it("renders without crashing", () => {
    render(<BrandDetailPage />);
    expect(document.body.querySelector("div")).toBeTruthy();
  });

  it("shows the brand name from URL param", () => {
    render(<BrandDetailPage />);
    // Brand name appears in both breadcrumb and h1
    expect(screen.getAllByText("TestBrand").length).toBeGreaterThanOrEqual(1);
  });

  it("shows breadcrumb with link to brands list", () => {
    render(<BrandDetailPage />);
    expect(screen.getByText("Brands")).toBeInTheDocument();
  });

  it("shows price basis in description", () => {
    render(<BrandDetailPage />);
    expect(
      screen.getByText(/P\/L = Actual Revenue.*GP Commission/i)
    ).toBeInTheDocument();
  });

  it("displays product data after loading", async () => {
    render(<BrandDetailPage />);
    const itemCode = await screen.findByText("IT001");
    expect(itemCode).toBeInTheDocument();
  });
});
