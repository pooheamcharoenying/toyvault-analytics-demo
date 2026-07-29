"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useRef, useEffect } from "react";
import { useAuthUser } from "@/components/AuthGate";
import ChangePasswordModal from "@/components/ChangePasswordModal";

/* ─────────────────────────────────────────────
   NAV_ITEMS — single source of truth for navigation.

   RULES (see CLAUDE.md §11):
   - Max 7 top-level items (including Home, Logout, and any standalone links)
   - Group related pages into dropdowns when total pages exceed what fits on a 1366px laptop
   - "Actions" (if built) should be standalone, not inside a group
   - Keep this array in sync with the Home page cards
   ───────────────────────────────────────────── */

const NAV_STANDALONE = [
  { href: "/", label: "Home" },
  { href: "/dashboards/ai-assist", label: "AI Assist" },
  { href: "/dashboards/actions", label: "Actions" },
  { href: "/dashboards/executive", label: "Executive" },
];

const NAV_GROUPS = [
  {
    label: "Inventory & Stock",
    items: [
      { href: "/dashboards/inventory-alerts", label: "Inventory Alerts" },
      { href: "/dashboards/planogram", label: "Planogram" },
      { href: "/dashboards/stock-allocation", label: "Stock Allocation" },
      { href: "/dashboards/stock-bot", label: "Stock Bot 🤖" },
      { href: "/dashboards/purchase-analytics", label: "Purchase Analytics" },
    ],
  },
  {
    label: "Analytics",
    items: [
      { href: "/dashboards/brands", label: "Brands & Products" },
      { href: "/dashboards/locations", label: "Locations & Stores" },
      { href: "/dashboards/channels", label: "Channels" },
      { href: "/dashboards/seasonality-margin", label: "Seasonality & Margin" },
    ],
  },
  {
    label: "Reports & Tools",
    items: [
      { href: "/task2", label: "Operations" },
      { href: "/dashboards/period-comparison", label: "Period Comparison" },
      { href: "/dashboards/data-quality", label: "Data Quality" },
      { href: "/task1", label: "Barcode Lookup" },
    ],
  },
];

// Flat list for mobile menu and tests
const ALL_NAV_ITEMS = [
  ...NAV_STANDALONE,
  ...NAV_GROUPS.flatMap((g) => g.items),
];

/* ─────────────────────────────────────────────
   Dropdown component for grouped nav items
   ───────────────────────────────────────────── */
function NavDropdown({ label, items, pathname }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  // Close on outside click
  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Close on Escape key
  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e) {
      if (e.key === "Escape") { setOpen(false); }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  const hasActive = items.some((i) => pathname === i.href);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="true"
        className={`flex items-center gap-1 px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-150 ${
          hasActive
            ? "bg-[var(--nichi-yellow)] text-[var(--nichi-blue-dark)] shadow-sm"
            : "text-white/85 hover:bg-white/10 hover:text-white"
        }`}
      >
        {label}
        <svg
          className={`w-3.5 h-3.5 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 w-56 bg-[var(--nichi-blue-dark)] rounded-lg shadow-xl border border-white/10 py-1 z-50">
          {items.map(({ href, label: itemLabel }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setOpen(false)}
                className={`block px-4 py-2 text-sm transition-all duration-100 ${
                  active
                    ? "bg-[var(--nichi-yellow)] text-[var(--nichi-blue-dark)] font-semibold"
                    : "text-white/85 hover:bg-white/10 hover:text-white"
                }`}
              >
                {itemLabel}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────
   Account dropdown (name → Connect LINE / change password / logout)
   ───────────────────────────────────────────── */
function AccountDropdown({ user, onChangePassword, onLinkLine, onLogout }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    function h(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  const name = user?.display_name || user?.username || "Account";
  return (
    <div ref={ref} className="relative ml-2">
      <button onClick={() => setOpen((o) => !o)}
              className="flex items-center gap-2 px-2 py-1.5 rounded-md text-sm text-white/85 hover:bg-white/10">
        <span className="w-6 h-6 rounded-full bg-[var(--nichi-yellow)] text-[var(--nichi-blue-dark)] flex items-center justify-center text-xs font-bold">
          {name[0]?.toUpperCase()}
        </span>
        <span className="max-w-[110px] truncate">{name}</span>
        <svg className={`w-3.5 h-3.5 transition-transform ${open ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-1 w-52 bg-[var(--nichi-blue-dark)] rounded-lg shadow-xl border border-white/10 py-1 z-50">
          {user?.username && (
            <div className="px-4 py-1.5 text-[11px] text-white/50 border-b border-white/10">
              Signed in as {user.username}{user.role === "admin" ? " · admin" : ""}
            </div>
          )}
          <button onClick={() => { setOpen(false); onLinkLine(); }}
                  className="block w-full text-left px-4 py-2 text-sm text-white/85 hover:bg-white/10">Connect LINE</button>
          <button onClick={() => { setOpen(false); onChangePassword(); }}
                  className="block w-full text-left px-4 py-2 text-sm text-white/85 hover:bg-white/10">Change password</button>
          <button onClick={() => { setOpen(false); onLogout(); }}
                  className="block w-full text-left px-4 py-2 text-sm text-white/85 hover:bg-white/10">Logout</button>
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────
   Main Navbar
   ───────────────────────────────────────────── */
export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const { user, logout } = useAuthUser() || {};

  const handleLogout = async () => {
    if (logout) await logout();
    router.push("/");
  };

  return (
    <nav className="no-print bg-black shadow-md">
      <div className="max-w-[1600px] mx-auto px-4 sm:px-6">
        <div className="flex items-center justify-between h-14">
          {/* Brand (text only, no logo) */}
          <Link href="/" className="flex items-center gap-2.5 shrink-0">
            <span className="text-white font-bold text-lg tracking-tight">
              TOY VAULT
            </span>
          </Link>

          {/* Desktop Nav — standalone links + grouped dropdowns */}
          <div className="hidden md:flex items-center gap-1">
            {NAV_STANDALONE.map(({ href, label }) => {
              const active = pathname === href;
              return (
                <Link
                  key={href}
                  href={href}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-150 ${
                    active
                      ? "bg-[var(--nichi-yellow)] text-[var(--nichi-blue-dark)] shadow-sm"
                      : "text-white/85 hover:bg-white/10 hover:text-white"
                  }`}
                >
                  {label}
                </Link>
              );
            })}

            {NAV_GROUPS.map((group) => (
              <NavDropdown
                key={group.label}
                label={group.label}
                items={group.items}
                pathname={pathname}
              />
            ))}

            <AccountDropdown
              user={user}
              onChangePassword={() => setShowPw(true)}
              onLinkLine={() => router.push("/dashboards/line-setup")}
              onLogout={handleLogout}
            />
          </div>

          {/* Mobile hamburger */}
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="md:hidden p-2 rounded-md text-white/85 hover:text-white hover:bg-white/10"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {menuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {/* Mobile menu — flat list grouped with headers */}
      {menuOpen && (
        <div className="md:hidden border-t border-white/10 px-4 py-2 space-y-1">
          {NAV_STANDALONE.map(({ href, label }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setMenuOpen(false)}
                className={`block px-3 py-2 rounded-md text-sm font-medium transition ${
                  active
                    ? "bg-[var(--nichi-yellow)] text-[var(--nichi-blue-dark)]"
                    : "text-white/85 hover:bg-white/10 hover:text-white"
                }`}
              >
                {label}
              </Link>
            );
          })}

          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <div className="px-3 pt-3 pb-1 text-xs font-semibold text-white/50 uppercase tracking-wider">
                {group.label}
              </div>
              {group.items.map(({ href, label }) => {
                const active = pathname === href;
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setMenuOpen(false)}
                    className={`block px-3 py-2 rounded-md text-sm font-medium transition ${
                      active
                        ? "bg-[var(--nichi-yellow)] text-[var(--nichi-blue-dark)]"
                        : "text-white/85 hover:bg-white/10 hover:text-white"
                    }`}
                  >
                    {label}
                  </Link>
                );
              })}
            </div>
          ))}

          <button
            onClick={() => { setMenuOpen(false); router.push("/dashboards/line-setup"); }}
            className="w-full text-left px-3 py-2 rounded-md text-sm text-white/80 hover:text-white hover:bg-white/10 transition"
          >
            Connect LINE
          </button>
          <button
            onClick={() => { setMenuOpen(false); setShowPw(true); }}
            className="w-full text-left px-3 py-2 rounded-md text-sm text-white/80 hover:text-white hover:bg-white/10 transition"
          >
            Change password
          </button>
          <button
            onClick={() => { setMenuOpen(false); handleLogout(); }}
            className="w-full text-left px-3 py-2 rounded-md text-sm text-white/60 hover:text-white hover:bg-white/10 transition"
          >
            Logout
          </button>
        </div>
      )}
      {showPw && <ChangePasswordModal onClose={() => setShowPw(false)} />}
    </nav>
  );
}

// Export for tests
export { ALL_NAV_ITEMS, NAV_STANDALONE, NAV_GROUPS };
