"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function NavBar() {
  const { logout } = useAuth();
  const router = useRouter();

  return (
    <header
      className="flex h-[60px] items-center justify-between px-6 animate-fade-in"
      style={{ borderBottom: "1px solid var(--hairline)" }}
    >
      <span
        className="font-display text-[20px] font-semibold leading-[1.4] text-ink"
        style={{ letterSpacing: "-0.3px" }}
      >
        Lumen
      </span>
      <button
        onClick={() => {
          logout();
          router.push("/login");
        }}
        className="font-ui rounded-full bg-surface-dark px-6 text-sm font-semibold leading-[1.0] text-on-dark transition-colors hover:bg-[#333]"
        style={{ height: "36px" }}
      >
        Sign Out
      </button>
    </header>
  );
}
