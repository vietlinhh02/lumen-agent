"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { isTokenExpired, TOKEN_KEY } from "@/lib/jwt";

export function Hero() {
  const router = useRouter();
  const [loggedIn, setLoggedIn] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const sectionRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    setLoggedIn(!!token && !isTokenExpired(token));
  }, []);

  useEffect(() => {
    const handleScroll = () => {
      if (rafRef.current) return;
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = 0;
        if (!imgRef.current || !sectionRef.current) return;
        const startY = sectionRef.current.offsetTop + sectionRef.current.offsetHeight - window.innerHeight;
        const endY = sectionRef.current.offsetTop + sectionRef.current.offsetHeight;
        const progress = Math.max(0, Math.min(1, (window.scrollY - startY) / (endY - startY)));
        const rotateX = -5 + progress * 8;
        const scale = 1 + progress * 0.1;
        imgRef.current.style.transform = `perspective(1000px) rotateX(${rotateX}deg) scale(${scale})`;
        imgRef.current.style.backfaceVisibility = "hidden";
        imgRef.current.style.webkitBackfaceVisibility = "hidden";
      });
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <section className="relative overflow-visible">
      {/* Atmospheric gradient mesh — stops before image */}
      <div className="absolute inset-0 -z-10 h-[85%] overflow-hidden">
        <div className="absolute left-1/2 top-0 h-[800px] w-[1200px] -translate-x-1/2 -translate-y-1/4 rounded-full bg-gradient-to-br from-primary/20 via-primary/10 to-transparent blur-3xl" />
        <div className="absolute right-0 top-1/3 h-[400px] w-[600px] rounded-full bg-gradient-to-l from-primary/5 to-transparent blur-2xl" />
      </div>

      {/* Hero heading + CTA — 2 lines max */}
      <div className="mx-auto max-w-4xl px-6 pb-12 pt-24 text-center lg:pt-32">
        <h1
          className="font-display text-4xl font-bold leading-[1.1] tracking-tight text-ink sm:text-5xl lg:text-6xl"
          style={{ letterSpacing: "-1.5px" }}
        >
          Stop losing weeks to literature reviews.
        </h1>

        <p className="mx-auto mt-4 max-w-2xl text-base leading-relaxed text-body sm:text-lg">
          Search across academic sources, build a structured evidence matrix,
          detect research gaps, and export citation-safe reviews — all in one workspace.
        </p>

        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <button
            onClick={() => router.push(loggedIn ? "/dashboard" : "/login")}
            className="inline-flex h-11 cursor-pointer items-center justify-center rounded-full bg-primary px-7 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep"
          >
            {loggedIn ? "Go to Dashboard" : "Start for free"}
          </button>
          <a
            href="#workflow"
            className="inline-flex h-11 items-center justify-center rounded-full border border-hairline-strong bg-surface-card px-7 text-sm font-semibold text-ink transition-colors hover:bg-surface-bone"
          >
            See how it works
          </a>
        </div>
      </div>

      {/* Image — straddles hero bg and surface-bone (desktop only) */}
      <div
        ref={sectionRef}
        className="relative z-10 mx-auto mb-0 w-full max-w-6xl overflow-visible px-4 pb-0 lg:-mb-44"
        style={{ perspective: "1000px" }}
      >
        <img
          ref={imgRef}
          src="/hero-screenshot.png"
          alt="AI Literature Review Assistant"
          className="mx-auto h-auto w-full rounded-2xl shadow-2xl"
          style={{
            transform: "rotateX(-8deg) scale(1)",
            transformStyle: "preserve-3d",
            backfaceVisibility: "hidden",
            WebkitBackfaceVisibility: "hidden" as any,
            willChange: "transform",
            transition: "transform 0.15s ease-out",
          }}
        />
      </div>
    </section>
  );
}
