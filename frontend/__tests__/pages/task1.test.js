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

import Task1 from "@/app/task1/page";

describe("Barcode Lookup Page (Task1)", () => {
  it("renders without crashing", () => {
    render(<Task1 />);
    expect(document.body.querySelector("div")).toBeTruthy();
  });

  it("has a textarea for barcode input", () => {
    render(<Task1 />);
    const textarea = document.body.querySelector("textarea");
    expect(textarea).toBeTruthy();
  });
});
