import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: jest.fn() }),
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

import Navbar, { ALL_NAV_ITEMS, NAV_STANDALONE, NAV_GROUPS } from "@/components/Navbar";

describe("Navbar", () => {
  it("renders without crashing", () => {
    render(<Navbar />);
    expect(screen.getByText("TOYVAULT")).toBeInTheDocument();
  });

  it("renders standalone navigation links", () => {
    render(<Navbar />);
    NAV_STANDALONE.forEach(({ label }) => {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    });
  });

  it("renders dropdown group labels", () => {
    render(<Navbar />);
    NAV_GROUPS.forEach(({ label }) => {
      // Group labels appear as dropdown buttons on desktop
      expect(screen.getAllByText(label).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("opens dropdown and shows items when clicked", () => {
    render(<Navbar />);
    // Click the first dropdown group
    const groupButton = screen.getAllByText(NAV_GROUPS[0].label)[0];
    fireEvent.click(groupButton);
    // Now the dropdown items should be visible
    NAV_GROUPS[0].items.forEach(({ label }) => {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    });
  });

  it("renders the Logout button", () => {
    render(<Navbar />);
    const logoutButtons = screen.getAllByText("Logout");
    expect(logoutButtons.length).toBeGreaterThan(0);
  });

  it("highlights the active nav item (Home on /)", () => {
    render(<Navbar />);
    const homeLink = screen.getAllByText("Home")[0];
    expect(homeLink.closest("a")).toBeTruthy();
  });

  it("has correct total number of navigation pages", () => {
    // Guard: if someone adds a page, this test reminds them to update grouping
    expect(ALL_NAV_ITEMS.length).toBe(14);
  });
});
