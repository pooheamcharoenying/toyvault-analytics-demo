import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock axios
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get: jest.fn(() => Promise.resolve({ data: {} })),
  post: jest.fn(() => Promise.resolve({ data: {} })),
    create: jest.fn(function () { return this; }),
    isCancel: jest.fn(() => false),
    interceptors: { response: { use: jest.fn() } },
  },
  get: jest.fn(() => Promise.resolve({ data: {} })),
  post: jest.fn(() => Promise.resolve({ data: {} })),
  isCancel: jest.fn(() => false),
}));

// Mock recharts
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => React.createElement("div", null, children),
  BarChart: ({ children }) => React.createElement("div", null, children),
  LineChart: ({ children }) => React.createElement("div", null, children),
  Bar: () => null,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  Cell: () => null,
}));

import Task2 from "@/app/task2/page";

describe("Operations Page (Task2)", () => {
  it("renders without crashing", () => {
    render(<Task2 />);
    expect(document.body.querySelector("div")).toBeTruthy();
  });
});
