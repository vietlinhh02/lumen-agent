"use client";

import { memo, useState, useRef, useEffect, useEffectEvent } from "react";
import Image from "next/image";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/lib/stores/auth-store";
import { useUIStore } from "@/lib/stores/ui-store";
import { useAssistantStore } from "@/lib/stores/assistant-store";
import { SessionList } from "@/components/assistant/SessionList";
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
  ChatCircle,
  Sliders,
  CaretDown,
} from "@phosphor-icons/react";

/* ── Navigation items ── */

const NAV_ITEMS = [
  { label: "Dashboard", href: "/dashboard", icon: SquaresFour },
  { label: "Projects", href: "/projects", icon: Folder },
  { label: "Search Papers", href: "/search", icon: MagnifyingGlass },
  { label: "Saved Papers", href: "/papers", icon: FileText },
  { label: "Matrix", href: "/matrix", icon: Table },
  { label: "Knowledge Map", href: "/map", icon: Graph },
  { label: "Gaps", href: "/gaps", icon: Lightbulb },
  { label: "Reports", href: "/reports", icon: PencilLine },
  { label: "Assistant", href: "/assistant", icon: ChatCircle },
  { label: "Settings", href: "/settings", icon: GearSix },
];

/* ── AppShell ── */

export function AppShell({ children }: { children: React.ReactNode }) {
  const sidebarOpen = useUIStore((s) => s.sidebarMobileOpen);
  const setSidebarOpen = useUIStore((s) => s.setSidebarMobileOpen);
  const pathname = usePathname();
  const isAssistant = pathname?.startsWith("/assistant") ?? false;

  return (
    <>
      <Header onMenuClick={() => setSidebarOpen(true)} />
      {/* Desktop sidebar */}
      <SidebarDesktop />
      {/* Mobile drawer */}
      <SidebarMobile open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <main
        className={
          isAssistant
            ? "h-[calc(100vh-60px)] overflow-hidden ml-0 xl:ml-[56px]"
            : "min-h-[calc(100vh-60px)] px-4 sm:px-8 pt-8 pb-12 ml-0 xl:ml-[56px]"
        }
      >
        {children}
      </main>
    </>
  );
}

/* ── Header ── */

const Header = memo(function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const token = useAuth((s) => s.token);
  const logout = useAuth((s) => s.logout);
  const userMenuOpen = useUIStore((s) => s.userMenuOpen);
  const setUserMenuOpen = useUIStore((s) => s.setUserMenuOpen);
  const router = useRouter();
  const pathname = usePathname();
  const isAssistant = pathname?.startsWith("/assistant") ?? false;
  const ref = useRef<HTMLDivElement>(null);

  const seed = token ?? "lumen";
  const avatarUrl = `https://api.dicebear.com/7.x/thumbs/svg?seed=${encodeURIComponent(seed)}`;

  useEffect(() => {
    if (!userMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setUserMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [userMenuOpen, setUserMenuOpen]);

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
        type="button"
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

      {/* Assistant page header controls (rendered only on /assistant/*) */}
      {isAssistant && <AssistantHeaderControls />}

      <div ref={ref} className="relative">
        <button
          type="button"
          onClick={() => setUserMenuOpen(!userMenuOpen)}
          className="flex h-[36px] w-[36px] items-center justify-center rounded-full overflow-hidden transition-all duration-200 hover:ring-2 hover:ring-primary/30"
        >
          <Image
            src={avatarUrl}
            alt="avatar"
            width={36}
            height={36}
            unoptimized
            className="h-full w-full"
          />
        </button>

        {userMenuOpen && (
          <div
            className="absolute right-0 top-[44px] z-50 w-[180px] rounded-[12px] bg-surface-dark p-1 shadow-lg"
            style={{ border: "1px solid var(--hairline)" }}
          >
            <button
              type="button"
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

/* ── Assistant page header controls ────────────────────────────────────── */

function AssistantHeaderControls() {
  const router = useRouter();
  const loadSessions = useAssistantStore((s) => s.loadSessions);
  const createSession = useAssistantStore((s) => s.createSession);
  const activeSessionId = useAssistantStore((s) => s.activeSessionId);
  const currentSession = useAssistantStore((s) => s.currentSession);
  const eventsMap = useAssistantStore((s) => s.events);

  const sessionsOpen = useUIStore((s) => s.assistantSessionsOpen);
  const setSessionsOpen = useUIStore((s) => s.setAssistantSessionsOpen);
  const toolPanelOpen = useUIStore((s) => s.assistantToolPanelOpen);
  const toggleToolPanel = useUIStore((s) => s.toggleAssistantToolPanel);
  const toggleSessions = useUIStore((s) => s.toggleAssistantSessions);

  // A "new" session is one that has no events yet. Disabling the New
  // action in that state prevents the user from spamming the API by
  // creating one empty session after another.
  const currentSessionEventCount = activeSessionId
    ? (eventsMap.get(activeSessionId)?.length ?? 0)
    : 0;
  const isCurrentSessionNew = activeSessionId !== null && currentSessionEventCount === 0;

  // Re-entrancy guard: prevent rapid clicks while a session is being
  // created (the createSession promise hasn't resolved yet).
  const [isCreating, setIsCreating] = useState(false);

  // Load sessions lazily when the dropdown is opened
  useEffect(() => {
    if (sessionsOpen) void loadSessions();
  }, [sessionsOpen, loadSessions]);

  // Close dropdown on route change
  useEffect(() => {
    setSessionsOpen(false);
  }, [activeSessionId, setSessionsOpen]);

  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click / Escape (mobile/tablet only)
  useEffect(() => {
    if (!sessionsOpen) return;
    const onMouse = (e: MouseEvent) => {
      // Ignore outside clicks for closing on desktop (>= 1280px)
      if (typeof window !== "undefined" && window.innerWidth >= 1280) return;
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setSessionsOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSessionsOpen(false);
    };
    document.addEventListener("mousedown", onMouse);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onMouse);
      document.removeEventListener("keydown", onKey);
    };
  }, [sessionsOpen, setSessionsOpen]);

  const handleNewChat = async () => {
    // Don't allow creating a new session while one is already in flight
    // or when the current session is still empty.
    if (isCreating) return;
    if (isCurrentSessionNew) return;

    setIsCreating(true);
    try {
      const session = await createSession();
      if (session) router.push(`/assistant/sessions/${session.id}`);
    } finally {
      setIsCreating(false);
    }
    // Only auto-close dropdown on mobile
    if (typeof window !== "undefined" && window.innerWidth < 1280) {
      setSessionsOpen(false);
    }
  };

  return (
    <div ref={dropdownRef} className="flex items-center gap-1 mr-2 relative">
      {/* Sessions dropdown trigger (hidden on desktop since we have the left toggle button) */}
      <button
        type="button"
        onClick={toggleSessions}
        className={`xl:hidden flex h-9 items-center gap-1.5 rounded-lg px-2.5 sm:px-3 font-ui text-sm transition-all duration-150 active:scale-95 ${
          sessionsOpen
            ? "bg-primary/10 text-primary"
            : "text-charcoal hover:text-ink hover:bg-surface-bone"
        }`}
        title="Recent chats"
      >
        <List size={18} weight="bold" />
        <span className="hidden sm:inline max-w-[160px] truncate">
          Recent chats
        </span>
        <CaretDown
          size={12}
          weight="bold"
          className={`transition-transform duration-200 ${sessionsOpen ? "rotate-180" : ""}`}
        />
      </button>

      {/* View tool (toggle right tool panel) */}
      <button
        type="button"
        onClick={toggleToolPanel}
        className={`flex h-9 w-9 sm:w-auto sm:px-2.5 items-center justify-center gap-1.5 rounded-lg transition-all duration-150 active:scale-95 ${
          toolPanelOpen
            ? "bg-primary/10 text-primary"
            : "text-charcoal hover:text-ink hover:bg-surface-bone"
        }`}
        title="Toggle tool panel"
        aria-label="Toggle tool panel"
      >
        <Sliders size={18} weight="bold" />
        <span className="hidden sm:inline font-ui text-sm font-medium">View tool</span>
      </button>

      {/* Dropdown — always rendered so we get a smooth enter animation.
          `pointer-events-none` keeps it inert when hidden. `overflow-hidden`
          keeps the inner SessionList clipped to the rounded corners. The
          DeleteSessionModal is rendered via portal (see SessionList), so
          it is NOT clipped by this overflow. Visible only on mobile/tablet (xl:hidden) */}
      <div
        className={`absolute right-0 top-[44px] z-50 w-[min(320px,calc(100vw-16px))] rounded-xl bg-canvas shadow-2xl overflow-hidden transition-all duration-200 ease-out origin-top-right xl:hidden ${
          sessionsOpen
            ? "opacity-100 translate-y-0 scale-100 pointer-events-auto"
            : "opacity-0 -translate-y-1 scale-95 pointer-events-none"
        }`}
        style={{ border: "1px solid var(--hairline)" }}
      >
        <SessionList
          compact
          isCurrentSessionNew={isCurrentSessionNew}
          isCreating={isCreating}
          onClose={() => setSessionsOpen(false)}
          onNewChat={handleNewChat}
          onSelectSession={() => setSessionsOpen(false)}
        />
      </div>
    </div>
  );
}

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
            type="button"
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
  const onCloseEvent = useEffectEvent(onClose);

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
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCloseEvent(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const closeSidebar = useUIStore((s) => s.closeSidebar);

  return (
    <>
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close sidebar"
        onClick={() => { onClose(); closeSidebar(); }}
        className={`xl:hidden fixed inset-0 z-30 bg-black/40 transition-opacity duration-300 ${
          open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
      />

      {/* Drawer */}
      <aside
        className={`xl:hidden fixed top-0 left-0 bottom-0 z-40 w-[280px] bg-canvas shadow-2xl transition-transform duration-300 ease-out flex flex-col ${
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
            type="button"
            onClick={() => { onClose(); closeSidebar(); }}
            className="flex h-[36px] w-[36px] items-center justify-center rounded-[10px] text-charcoal hover:text-ink hover:bg-surface-bone transition-colors"
          >
            <X size={20} weight="bold" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          <nav className="p-3 flex flex-col gap-0.5">
            <NavItemsMobile onClose={onClose} />
          </nav>
        </div>
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
            type="button"
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
