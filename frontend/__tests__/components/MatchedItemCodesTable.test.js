import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import MatchedItemCodesTable from "@/components/MatchedItemCodesTable";

describe("MatchedItemCodesTable", () => {
  it("renders without crashing with empty array", () => {
    render(<MatchedItemCodesTable matchedItemCodes={[]} />);
    expect(screen.getByText("Matched Item Codes")).toBeInTheDocument();
  });

  it("renders item codes in a table", () => {
    const codes = ["ITEM001", "ITEM002", "ITEM003"];
    render(<MatchedItemCodesTable matchedItemCodes={codes} />);
    expect(screen.getByText("ITEM001")).toBeInTheDocument();
    expect(screen.getByText("ITEM002")).toBeInTheDocument();
    expect(screen.getByText("ITEM003")).toBeInTheDocument();
  });

  it("has a Copy button", () => {
    render(<MatchedItemCodesTable matchedItemCodes={["A"]} />);
    expect(screen.getByText("Copy")).toBeInTheDocument();
  });

  it("renders the table header", () => {
    render(<MatchedItemCodesTable matchedItemCodes={["A"]} />);
    expect(screen.getByText("Item Code")).toBeInTheDocument();
  });
});
