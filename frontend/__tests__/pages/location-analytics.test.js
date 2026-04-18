import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/dashboards/location-analytics",
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

import LocationAnalyticsPage from "@/app/dashboards/location-analytics/page";

describe("Location Analytics Page (redirect)", () => {
  it("renders without crashing", () => {
    render(<LocationAnalyticsPage />);
    expect(screen.getByText(/Redirecting to Locations/)).toBeInTheDocument();
  });
});
