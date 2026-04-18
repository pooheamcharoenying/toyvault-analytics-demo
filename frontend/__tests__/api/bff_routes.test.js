/**
 * BFF API Route Tests
 *
 * These tests verify that all BFF proxy routes export the correct HTTP handlers.
 * Since the route modules import from "next/server" which requires Node.js Web API
 * globals (Request, Response, Headers), we mock next/server to provide NextResponse.
 */

// Mock next/server BEFORE any route imports
jest.mock("next/server", () => {
  return {
    NextResponse: {
      json: (data, init) => {
        return {
          status: init?.status || 200,
          json: async () => data,
          _body: data,
        };
      },
    },
  };
});

// Mock axios
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
  post: jest.fn(),
    create: jest.fn(function () { return this; }),
    isCancel: jest.fn(() => false),
    interceptors: { response: { use: jest.fn() } },
  },
  get: jest.fn(),
  post: jest.fn(),
  isCancel: jest.fn(() => false),
}));

// Clear env vars
const ORIGINAL_ENV = { ...process.env };

beforeEach(() => {
  delete process.env.API_BASE_URL;
  delete process.env.NEXT_PUBLIC_API_URL;
  delete process.env.API_BASIC_USER;
  delete process.env.API_BASIC_PASS;
});

afterAll(() => {
  process.env = ORIGINAL_ENV;
});

// All GET routes
const GET_ROUTES = [
  "data_status",
  "data_line_counts",
  "executive_summary",
  "sales_trend_executive",
  "concentration_summary",
  "store_health_summary",
  "margin_by_brand",
  "inventory_risk_summary",
  "channel_performance_executive",
  "product_sale_vs_onhand",
  "product_sale_vs_onhand_locations",
  "sale_brand_profit_loss",
  "sale_brand_item_locations",
  "sale_brand_item_channels",
  "get_brand_list",
  "get_channel_list",
  "get_file_date",
  "sale_brand_channel",
  "sale_channel_brand",
  "locations_sale_onhand_summary",
  "sale_record_by_brand",
  "sale_record_by_channel",
  "stockout_risk",
  "dead_stock",
  "reorder_analysis",
  "abc_classification",
  "product_channel_fit",
  "location_performance",
  "location_trends",
  "location_product_mix",
  "purchase_cost_trends",
  "purchase_vs_sold",
  "working_capital_trends",
  "seasonality_analysis",
  "margin_mix_analysis",
  "stock_allocation",
  "transfer_history",
  "rebalancing_summary",
  "period_comparison",
  "priority_actions",
];

describe("BFF GET routes export GET handler", () => {
  GET_ROUTES.forEach((route) => {
    it(`/api/${route} exports a GET function`, async () => {
      const mod = await import(`@/app/api/${route}/route`);
      expect(typeof mod.GET).toBe("function");
    });
  });
});

describe("BFF POST routes export POST handler", () => {
  it("/api/match exports a POST function", async () => {
    const mod = await import("@/app/api/match/route");
    expect(typeof mod.POST).toBe("function");
  });

  it("/api/brand_health_summary exports a POST function", async () => {
    const mod = await import("@/app/api/brand_health_summary/route");
    expect(typeof mod.POST).toBe("function");
  });
});

describe("BFF routes return error when env vars missing", () => {
  it("GET /api/data_status returns 500 when env missing", async () => {
    const mod = await import("@/app/api/data_status/route");
    const response = await mod.GET();
    const json = await response.json();
    expect(response.status).toBe(500);
    expect(json).toHaveProperty("error");
  });

  it("GET /api/executive_summary returns 500 when env missing", async () => {
    const mod = await import("@/app/api/executive_summary/route");
    const response = await mod.GET();
    const json = await response.json();
    expect(response.status).toBe(500);
    expect(json).toHaveProperty("error");
  });

  it("POST /api/match returns 500 when env missing", async () => {
    const mod = await import("@/app/api/match/route");
    const req = {
      json: async () => ({ barcodes: ["123"] }),
      url: "http://localhost:3000/api/match",
    };
    const response = await mod.POST(req);
    const json = await response.json();
    expect(response.status).toBe(500);
    expect(json).toHaveProperty("error");
  });
});
