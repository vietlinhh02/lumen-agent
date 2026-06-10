"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { List, X } from "@phosphor-icons/react";
import { isTokenExpired, TOKEN_KEY } from "@/lib/jwt";

const navLinks = [
  { label: "Workflow", href: "#workflow" },
  { label: "Features", href: "#features" },
  { label: "Why Lumen", href: "#pain-points" },
];

export function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    setLoggedIn(!!token && !isTokenExpired(token));
  }, []);

  function handleAuthClick() {
    router.push("/login");
  }

  function handleDashboardClick() {
    router.push("/dashboard");
  }

  return (
    <nav className="sticky top-0 z-50 border-b border-hairline bg-canvas/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2">
          <span
            className="font-display text-xl font-bold text-ink"
            style={{ letterSpacing: "-0.5px" }}
          >
            Lumen
          </span>
        </Link>

        {/* Desktop nav */}
        <div className="hidden items-center gap-8 md:flex">
          {navLinks.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-sm font-medium text-charcoal transition-colors hover:text-ink"
            >
              {link.label}
            </a>
          ))}
        </div>

        <div className="hidden items-center gap-3 md:flex">
          {loggedIn ? (
            <button
              onClick={handleDashboardClick}
              className="cursor-pointer rounded-full bg-primary px-5 py-2 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep"
            >
              Dashboard
            </button>
          ) : (
            <>
              <button
                onClick={handleAuthClick}
                className="cursor-pointer rounded-full px-5 py-2 text-sm font-semibold text-ink transition-colors hover:bg-surface-bone"
              >
                Sign in
              </button>
              <button
                onClick={handleAuthClick}
                className="cursor-pointer rounded-full bg-primary px-5 py-2 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep"
              >
                Get Started
              </button>
            </>
          )}
        </div>

        {/* Mobile hamburger */}
        <button
          className="flex h-10 w-10 items-center justify-center rounded-full text-ink md:hidden"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle menu"
        >
          {mobileOpen ? <X size={24} /> : <List size={24} />}
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="border-t border-hairline bg-canvas px-6 pb-6 pt-4 md:hidden">
          <div className="flex flex-col gap-4">
            {navLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="text-sm font-medium text-charcoal transition-colors hover:text-ink"
                onClick={() => setMobileOpen(false)}
              >
                {link.label}
              </a>
            ))}
            <div className="mt-2 flex flex-col gap-2">
              {loggedIn ? (
                <button
                  onClick={() => { setMobileOpen(false); handleDashboardClick(); }}
                  className="cursor-pointer rounded-full bg-primary px-5 py-2 text-center text-sm font-semibold text-on-primary"
                >
                  Dashboard
                </button>
              ) : (
                <>
                  <button
                    onClick={() => { setMobileOpen(false); handleAuthClick(); }}
                    className="cursor-pointer rounded-full border border-hairline-strong px-5 py-2 text-center text-sm font-semibold text-ink"
                  >
                    Sign in
                  </button>
                  <button
                    onClick={() => { setMobileOpen(false); handleAuthClick(); }}
                    className="cursor-pointer rounded-full bg-primary px-5 py-2 text-center text-sm font-semibold text-on-primary"
                  >
                    Get Started
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
