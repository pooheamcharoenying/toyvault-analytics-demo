import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock next/image
jest.mock("next/image", () => ({
  __esModule: true,
  default: (props) => React.createElement("img", { ...props, src: props.src }),
}));

// Mock js-cookie
const mockCookieGet = jest.fn();
const mockCookieSet = jest.fn();
jest.mock("js-cookie", () => ({
  get: (...args) => mockCookieGet(...args),
  set: (...args) => mockCookieSet(...args),
  remove: jest.fn(),
}));

import PasswordGate from "@/components/PasswordGate";

describe("PasswordGate", () => {
  beforeEach(() => {
    mockCookieGet.mockReset();
    mockCookieSet.mockReset();
  });

  it("shows login form when not authenticated", () => {
    mockCookieGet.mockReturnValue(undefined);
    render(
      <PasswordGate>
        <div>Protected Content</div>
      </PasswordGate>
    );
    expect(screen.getByText("Sign In")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Enter password")).toBeInTheDocument();
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
  });

  it("shows children when authenticated via cookie", () => {
    mockCookieGet.mockReturnValue("true");
    render(
      <PasswordGate>
        <div>Protected Content</div>
      </PasswordGate>
    );
    expect(screen.getByText("Protected Content")).toBeInTheDocument();
    expect(screen.queryByText("Sign In")).not.toBeInTheDocument();
  });

  it("renders the ToyVault branding on login page", () => {
    mockCookieGet.mockReturnValue(undefined);
    render(
      <PasswordGate>
        <div>Child</div>
      </PasswordGate>
    );
    expect(screen.getByText("TOYVAULT")).toBeInTheDocument();
    expect(screen.getByText("Business Analytics Dashboard")).toBeInTheDocument();
  });

  it("has a password input field", () => {
    mockCookieGet.mockReturnValue(undefined);
    render(
      <PasswordGate>
        <div>Child</div>
      </PasswordGate>
    );
    const input = screen.getByPlaceholderText("Enter password");
    expect(input).toHaveAttribute("type", "password");
  });
});
