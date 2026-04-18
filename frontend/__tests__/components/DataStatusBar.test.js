import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock axios
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    create: jest.fn(function () { return this; }),
    isCancel: jest.fn(() => false),
    interceptors: { response: { use: jest.fn() } },
  },
  get: jest.fn(),
  isCancel: jest.fn(() => false),
}));

import axios from "axios";
import DataStatusBar from "@/components/DataStatusBar";

describe("DataStatusBar", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders without crashing", () => {
    axios.get.mockRejectedValue(new Error("no server"));
    render(<DataStatusBar />);
    // Component renders a div with role="status"
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows 'Data ready' when backend reports ready state", async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes("data_status")) {
        return Promise.resolve({ data: { state: "ready", filename: "test.xlsx" } });
      }
      if (url.includes("data_line_counts")) {
        return Promise.resolve({ data: { sale: 1000, onhand: 200, master: 150, grpo_detail: 500, whs_code: 10, filedate: "2026-04-10" } });
      }
      return Promise.reject(new Error("unknown"));
    });

    render(<DataStatusBar />);
    await waitFor(() => {
      expect(screen.getByText("Data ready")).toBeInTheDocument();
    });
  });

  it("shows total row count and file date when data is ready", async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes("data_status")) {
        return Promise.resolve({ data: { state: "ready", filename: "test.xlsx" } });
      }
      if (url.includes("data_line_counts")) {
        return Promise.resolve({ data: { sale: 1000, onhand: 200, master: 150, grpo_detail: 500, whs_code: 10, filedate: "2026-04-10" } });
      }
      return Promise.reject(new Error("unknown"));
    });

    render(<DataStatusBar />);
    await waitFor(() => {
      expect(screen.getByText(/1,860 rows loaded/)).toBeInTheDocument();
      expect(screen.getByText(/As of: 2026-04-10/)).toBeInTheDocument();
    });
  });

  it("shows loading state when backend is loading", async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes("data_status")) {
        return Promise.resolve({ data: { state: "loading" } });
      }
      return Promise.resolve({ data: null });
    });

    render(<DataStatusBar />);
    await waitFor(() => {
      expect(screen.getByText("Loading workbook...")).toBeInTheDocument();
    });
  });

  it("shows error state when backend reports error", async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes("data_status")) {
        return Promise.resolve({ data: { state: "error", error: "Failed to load" } });
      }
      return Promise.resolve({ data: null });
    });

    render(<DataStatusBar />);
    await waitFor(() => {
      expect(screen.getByText("Load error")).toBeInTheDocument();
    });
  });
});
