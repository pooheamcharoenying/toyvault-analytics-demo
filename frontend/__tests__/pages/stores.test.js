import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  usePathname: () => "/dashboards/stores",
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

import StoresDashboardPage from "@/app/dashboards/stores/page";

describe("Store Scorecard Page (redirect)", () => {
  it("renders without crashing", () => {
    render(<StoresDashboardPage />);
    expect(screen.getByText(/Redirecting to Locations/)).toBeInTheDocument();
  });
});
