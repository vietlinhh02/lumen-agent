"use client";

import { memo, useState, useRef, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  SquaresFour,
  Folder,
  MagnifyingGlass,
  FileText,
  Table,
  Graph,
  Lightbulb,
  PencilLine,
  GearSix,
  SignOut,
} from "@phosphor-icons/react";

/* ── Navigation items ── */

const NAV_ITEMS = [
  { label: "Dashboard", href: "/", icon: SquaresFour },
  { label: "Projects", href: "/projects", icon: Folder },
  { label: "Search Papers", href: "/search", icon: MagnifyingGlass },
  { label: "Saved Papers", href: "/papers", icon: FileText },
  { label: "Matrix", href: "/matrix", icon: Table },
  { label: "Knowledge Map", href: "/map", icon: Graph },
  { label: "Gaps", href: "/gaps", icon: Lightbulb },
  { label: "Reports", href: "/reports", icon: PencilLine },
  { label: "Settings", href: "/settings", icon: GearSix },
];

/* ── AppShell ── */

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Header />
      <Sidebar />
      <main className="min-h-[calc(100vh-60px)] px-8 pt-8 pb-12" style={{ marginLeft: "56px" }}>
        {children}
      </main>
    </>
  );
}

/* ── Header (memoized — doesn't re-render on route change) ── */

const Header = memo(function Header() {
  const { token, logout } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);

  const seed = mounted && token ? token : "lumen";
  const avatarUrl = `https://api.dicebear.com/7.x/thumbs/svg?seed=${encodeURIComponent(seed)}`;

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleSignOut = () => {
    logout();
    router.push("/login");
  };

  return (
    <header
      className="sticky top-0 z-20 flex h-[60px] items-center px-6 bg-canvas"
      style={{ borderBottom: "1px solid var(--hairline)" }}
    >
      <span
        className="font-display text-[20px] font-semibold leading-[1.4] text-ink"
        style={{ letterSpacing: "-0.3px" }}
      >
        Lumen
      </span>

      <div className="flex-1" />

      <div ref={ref} className="relative">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex h-[36px] w-[36px] items-center justify-center rounded-full overflow-hidden transition-all duration-200 hover:ring-2 hover:ring-primary/30"
        >
          <img src={avatarUrl} alt="avatar" className="h-full w-full" />
        </button>

        {open && (
          <div
            className="absolute right-0 top-[44px] z-50 w-[180px] rounded-[12px] bg-surface-dark p-1 shadow-lg"
            style={{ border: "1px solid var(--hairline)" }}
          >
            <button
              onClick={handleSignOut}
              className="flex w-full items-center gap-2 rounded-[8px] px-3 py-2 font-ui text-sm text-on-dark transition-colors duration-150 hover:bg-[#333]"
            >
              <SignOut size={16} />
              Sign Out
            </button>
          </div>
        )}
      </div>
    </header>
  );
});

/* ── Sidebar ── */

function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();

  return (
    <aside
      className="fixed top-[60px] left-0 bottom-0 z-10 flex w-[56px] flex-col items-center py-4 bg-canvas"
      style={{ borderRight: "1px solid var(--hairline)" }}
    >
      <nav className="flex flex-col items-center gap-1">
        {NAV_ITEMS.map(({ label, href, icon: Icon }) => {
          const isActive =
            pathname === href ||
            (href !== "/" && pathname.startsWith(href));

          return (
            <button
              key={href}
              onClick={() => router.push(href)}
              className="sidebar-icon group relative flex h-[42px] w-[42px] items-center justify-center rounded-[12px] transition-all duration-200"
            >
              {isActive && (
                <span className="absolute left-[-4px] top-1/2 -translate-y-1/2 h-[18px] w-[3px] rounded-full bg-primary" />
              )}

              <Icon
                size={22}
                weight={isActive ? "fill" : "regular"}
                className={`relative z-[1] transition-colors duration-200 ${
                  isActive ? "text-primary" : "text-charcoal group-hover:text-ink"
                }`}
              />

              <span className="pointer-events-none absolute left-[52px] z-50 whitespace-nowrap rounded-[8px] bg-surface-dark px-2.5 py-1.5 font-ui text-[12px] font-medium text-on-dark opacity-0 -translate-x-1 transition-all duration-150 group-hover:opacity-100 group-hover:translate-x-0">
                {label}
              </span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
