import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  usePathname: () => "/dashboards/item-detail/A001",
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
  useParams: () => ({ itemCode: "A001" }),
}));

// Mock next/image
jest.mock("next/image", () => ({
  __esModule: true,
  default: (props) => React.createElement("img", { ...props, src: props.src }),
}));

// Mock next/link
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...props }) =>
    React.createElement("a", { href, ...props }, children),
}));

// Mock js-cookie
jest.mock("js-cookie", () => ({
  get: jest.fn(() => "true"),
  set: jest.fn(),
  remove: jest.fn(),
}));

// Mock recharts
jest.mock("recharts", () => {
  const React = require("react");
  return {
    ResponsiveContainer: ({ children }) => React.createElement("div", null, children),
    BarChart: ({ children }) => React.createElement("div", null, children),
    Bar: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    Legend: () => null,
  };
});

const mockItemData = {
  found: true,
  item_info: {
    item_code: "A001",
    item_name: "Widget Alpha",
    brand: "BrandA",
    master_price: 100,
    total_onhand_qty: 80,
    total_onhand_thb: 8000,
    total_sold_qty: 50,
    total_sold_thb: 5000,
    total_sold_master_thb: 5000,
  },
  locations: [
    {
      whs_code: "WH01",
      whs_name: "Main Warehouse",
      onhand_qty: 50,
      onhand_thb: 5000,
      lifetime_sold_qty: 30,
      lifetime_sold_thb: 3000,
      lifetime_sold_master_thb: 3000,
    },
    {
      whs_code: "WH02",
      whs_name: "Shop Downtown",
      onhand_qty: 30,
      onhand_thb: 3000,
      lifetime_sold_qty: 20,
      lifetime_sold_thb: 2000,
      lifetime_sold_master_thb: 2000,
    },
  ],
};

// Mock axios (used by @/utils/api)
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get: jest.fn(() => Promise.resolve({ data: mockItemData })),
    post: jest.fn(() => Promise.resolve({ data: {} })),
    create: jest.fn(function () { return this; }),
    isCancel: jest.fn(() => false),
    interceptors: { response: { use: jest.fn() } },
  },
  get: jest.fn(() => Promise.resolve({ data: mockItemData })),
  post: jest.fn(() => Promise.resolve({ data: {} })),
  isCancel: jest.fn(() => false),
}));

import ItemDetailPage from "@/app/dashboards/item-detail/[itemCode]/page";

describe("Item Detail Page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Re-setup the mock return value after clearAllMocks
    const axios = require("axios");
    axios.default.get.mockResolvedValue({ data: mockItemData });
  });

  it("renders without crashing", async () => {
    render(<ItemDetailPage />);
    // Should show loading initially
    expect(screen.getByText(/loading item details/i)).toBeInTheDocument();
  });

  it("shows breadcrumb navigation", () => {
    render(<ItemDetailPage />);
    expect(screen.getByText("Brands")).toBeInTheDocument();
  });

  it("calls the API with the correct item code", () => {
    render(<ItemDetailPage />);
    const axios = require("axios");
    // API call now uses URLSearchParams with item_code and year_list
    const callArgs = axios.default.get.mock.calls[0];
    expect(callArgs[0]).toMatch(/\/api\/item_location_detail\?item_code=A001/);
    expect(callArgs[0]).toMatch(/year_list=/);
  });

  it("displays item details after loading", async () => {
    render(<ItemDetailPage />);
    // Wait for data to load
    const itemCode = await screen.findByText("A001");
    expect(itemCode).toBeInTheDocument();
    expect(screen.getByText("Widget Alpha")).toBeInTheDocument();
    expect(screen.getAllByText("BrandA").length).toBeGreaterThanOrEqual(1);
  });

  it("shows location detail table after loading", async () => {
    render(<ItemDetailPage />);
    const location = await screen.findByText("Main Warehouse");
    expect(location).toBeInTheDocument();
    expect(screen.getByText("Shop Downtown")).toBeInTheDocument();
  });

  it("has Export CSV button", async () => {
    render(<ItemDetailPage />);
    const csvButton = await screen.findByText("Export CSV");
    expect(csvButton).toBeInTheDocument();
  });
});
