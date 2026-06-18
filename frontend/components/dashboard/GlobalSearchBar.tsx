"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { MagnifyingGlass } from "@phosphor-icons/react";

export function GlobalSearchBar() {
  const [query, setQuery] = useState("");
  const router = useRouter();

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    router.push("/papers?q=" + encodeURIComponent(q));
  }

  return (
    <form
      onSubmit={handleSearch}
      className="mb-8 animate-fade-in-up delay-300"
    >
      <div className="relative">
        <MagnifyingGlass
          size={18}
          className="absolute left-4 top-1/2 -translate-y-1/2 text-ash"
        />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search papers across all projects..."
          className="focus-ring h-12 w-full rounded-full bg-surface-card pl-12 pr-36 text-base text-ink placeholder:text-ash outline-none transition-shadow"
          style={{ border: "1px solid var(--hairline)" }}
        />
        <button
          type="submit"
          disabled={!query.trim()}
          className="focus-ring absolute right-2 top-1/2 -translate-y-1/2 h-8 rounded-full bg-primary px-4 font-ui text-[13px] font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-40"
        >
          Search
        </button>
      </div>
    </form>
  );
}
