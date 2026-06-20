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
      className="mb-5 animate-fade-in-up delay-300 sm:mb-8"
    >
      <div className="relative grid gap-2 sm:block">
        <MagnifyingGlass
          size={18}
          className="pointer-events-none absolute left-4 top-6 -translate-y-1/2 text-ash sm:top-1/2"
        />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search papers across all projects..."
          className="focus-ring h-12 w-full rounded-full bg-surface-card pl-12 pr-4 text-sm text-ink placeholder:text-ash outline-none transition-shadow sm:pr-36 sm:text-base"
          style={{ border: "1px solid var(--hairline)" }}
        />
        <button
          type="submit"
          disabled={!query.trim()}
          className="focus-ring h-10 rounded-full bg-primary px-4 font-ui text-[13px] font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-40 sm:absolute sm:right-2 sm:top-1/2 sm:h-8 sm:-translate-y-1/2"
        >
          Search
        </button>
      </div>
    </form>
  );
}
