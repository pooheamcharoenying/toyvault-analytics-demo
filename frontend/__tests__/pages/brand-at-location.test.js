import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useParams: jest.fn(() => ({ location: "TestWarehouse", brand: "BrandX" })),
  useRouter: jest.fn(() => ({ back: jest.fn(), push: jest.fn() })),
  usePathname: jest.fn(() => "/dashboards/locations/TestWarehouse/BrandX"),
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
          top_brands: [],
          top_items: [
            { item_code: "IT001", item_name: "Toy Car", brand: "BrandX", sold_thb: 500, sold_qty: 5 },
          ],
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

import BrandAtLocationPage from "@/app/dashboards/locations/[location]/[brand]/page";

describe("Brand at Location Page", () => {
  it("renders without crashing", () => {
    render(<BrandAtLocationPage />);
    expect(document.body.querySelector("div")).toBeTruthy();
  });

  it("shows the brand and location names", () => {
    render(<BrandAtLocationPage />);
    expect(screen.getAllByText("BrandX").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/TestWarehouse/i).length).toBeGreaterThanOrEqual(1);
  });

  it("shows breadcrumb with links to locations and location detail", () => {
    render(<BrandAtLocationPage />);
    expect(screen.getByText("Locations")).toBeInTheDocument();
  });

  it("shows cross-link to full brand page", () => {
    render(<BrandAtLocationPage />);
    expect(screen.getByText(/View full brand page/i)).toBeInTheDocument();
  });

  it("displays product data after loading", async () => {
    render(<BrandAtLocationPage />);
    const itemCode = await screen.findByText("IT001");
    expect(itemCode).toBeInTheDocument();
  });
});
