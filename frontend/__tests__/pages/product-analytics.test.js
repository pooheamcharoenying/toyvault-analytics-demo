import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  usePathname: () => "/dashboards/product-analytics",
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), replace: jest.fn() }),
}));

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

import ProductAnalyticsPage from "@/app/dashboards/product-analytics/page";

describe("Product Analytics Page (redirect)", () => {
  it("renders without crashing", () => {
    render(<ProductAnalyticsPage />);
    expect(screen.getByText(/Redirecting to Brands/)).toBeInTheDocument();
  });
});
