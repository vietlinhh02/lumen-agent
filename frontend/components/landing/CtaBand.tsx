"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { isTokenExpired, TOKEN_KEY } from "@/lib/jwt";

export function CtaBand() {
  const router = useRouter();
  const [loggedIn, setLoggedIn] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    setLoggedIn(!!token && !isTokenExpired(token));
  }, []);

  return (
    <section className="relative overflow-hidden bg-primary py-24 lg:py-32">
      <div className="absolute left-1/2 top-1/2 h-[600px] w-[800px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-br from-primary-deep/50 to-transparent blur-3xl" />

      <div className="relative mx-auto max-w-7xl px-6 text-center">
        <h2
          className="font-display text-4xl font-bold leading-[1.0] text-on-dark sm:text-5xl lg:text-6xl"
          style={{ letterSpacing: "-1.5px" }}
        >
          Ready to illuminate
          <br />
          your research?
        </h2>
        <p className="mx-auto mt-6 max-w-md text-lg text-on-dark-mute">
          Build defensible literature reviews with real papers, structured
          evidence, and validated citations.
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <button
            onClick={() => router.push(loggedIn ? "/dashboard" : "/login")}
            className="inline-flex h-12 cursor-pointer items-center justify-center rounded-full bg-surface-dark px-8 text-base font-semibold text-on-dark transition-colors hover:bg-surface-deep"
          >
            {loggedIn ? "Go to Dashboard" : "Get started free"}
          </button>
          <a
            href="#workflow"
            className="inline-flex h-12 items-center justify-center rounded-full border border-[rgba(255,255,255,0.3)] px-8 text-base font-semibold text-on-dark transition-colors hover:bg-[rgba(255,255,255,0.1)]"
          >
            Learn more
          </a>
        </div>
      </div>
    </section>
  );
}
