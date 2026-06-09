"use client";

import { memo, useState, useRef, useEffect, useCallback } from "react";
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
  List,
  X,
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

/* ── Sidebar Context ── */

import { createContext, useContext } from "react";

type SidebarCtx = { open: boolean; setOpen: (v: boolean) => void };
const SidebarContext = createContext<SidebarCtx>({ open: false, setOpen: () => {} });
const useSidebar = () => useContext(SidebarContext);

/* ── AppShell ── */

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <SidebarContext.Provider value={{ open: mobileOpen, setOpen: setMobileOpen }}>
      <Header onMenuClick={() => setMobileOpen(true)} />
      {/* Desktop sidebar */}
      <SidebarDesktop />
      {/* Mobile drawer */}
      <SidebarMobile open={mobileOpen} onClose={() => setMobileOpen(false)} />
      <main className="min-h-[calc(100vh-60px)] px-4 sm:px-8 pt-8 pb-12 ml-0 xl:ml-[56px]">
        {children}
      </main>
    </SidebarContext.Provider>
  );
}

/* ── Header ── */

const Header = memo(function Header({ onMenuClick }: { onMenuClick: () => void }) {
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
      className="sticky top-0 z-20 flex h-[60px] items-center px-4 sm:px-6 bg-canvas"
      style={{ borderBottom: "1px solid var(--hairline)" }}
    >
      {/* Hamburger — mobile only */}
      <button
        onClick={onMenuClick}
        className="xl:hidden flex h-[36px] w-[36px] items-center justify-center rounded-[10px] text-charcoal hover:text-ink hover:bg-surface-bone transition-colors mr-3"
      >
        <List size={22} weight="bold" />
      </button>

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

/* ── Nav Items renderer (shared) ── */

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  const router = useRouter();
  const pathname = usePathname();

  return (
    <>
      {NAV_ITEMS.map(({ label, href, icon: Icon }) => {
        const isActive =
          pathname === href ||
          (href !== "/" && pathname.startsWith(href));

        return (
          <button
            key={href}
            onClick={() => {
              router.push(href);
              onNavigate?.();
            }}
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
    </>
  );
}

/* ── Desktop Sidebar ── */

function SidebarDesktop() {
  return (
    <aside
      className="hidden xl:flex fixed top-[60px] left-0 bottom-0 z-10 w-[56px] flex-col items-center py-4 bg-canvas"
      style={{ borderRight: "1px solid var(--hairline)" }}
    >
      <nav className="flex flex-col items-center gap-1">
        <NavItems />
      </nav>
    </aside>
  );
}

/* ── Mobile Sidebar (drawer) ── */

function SidebarMobile({ open, onClose }: { open: boolean; onClose: () => void }) {
  // Lock body scroll
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  // Close on escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        className={`xl:hidden fixed inset-0 z-30 bg-black/40 transition-opacity duration-300 ${
          open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
      />

      {/* Drawer */}
      <aside
        className={`xl:hidden fixed top-0 left-0 bottom-0 z-40 w-[280px] bg-canvas shadow-2xl transition-transform duration-300 ease-out ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{ borderRight: "1px solid var(--hairline)" }}
      >
        {/* Drawer header */}
        <div className="flex items-center justify-between h-[60px] px-5" style={{ borderBottom: "1px solid var(--hairline)" }}>
          <span className="font-display text-[20px] font-semibold text-ink" style={{ letterSpacing: "-0.3px" }}>
            Lumen
          </span>
          <button
            onClick={onClose}
            className="flex h-[36px] w-[36px] items-center justify-center rounded-[10px] text-charcoal hover:text-ink hover:bg-surface-bone transition-colors"
          >
            <X size={20} weight="bold" />
          </button>
        </div>

        {/* Nav items — full width with labels */}
        <nav className="p-3 flex flex-col gap-0.5">
          <NavItemsMobile onClose={onClose} />
        </nav>
      </aside>
    </>
  );
}

/* ── Mobile nav (with labels, no tooltip) ── */

function NavItemsMobile({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const pathname = usePathname();

  return (
    <>
      {NAV_ITEMS.map(({ label, href, icon: Icon }) => {
        const isActive =
          pathname === href ||
          (href !== "/" && pathname.startsWith(href));

        return (
          <button
            key={href}
            onClick={() => {
              router.push(href);
              onClose();
            }}
            className={`flex items-center gap-3 rounded-[10px] px-3 py-2.5 font-ui text-[14px] font-medium transition-all duration-150 text-left ${
              isActive
                ? "bg-primary/10 text-primary"
                : "text-charcoal hover:bg-surface-bone hover:text-ink"
            }`}
          >
            <Icon size={20} weight={isActive ? "fill" : "regular"} />
            {label}
          </button>
        );
      })}
    </>
  );
}
