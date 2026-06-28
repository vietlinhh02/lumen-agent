/* eslint-disable */
"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { isTokenExpired } from "@/lib/jwt";
import { useAuthStore } from "@/lib/stores/auth-store";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { MagneticButton } from "./MagneticButton";

export function Hero() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const [loggedIn, setLoggedIn] = useState(false);
  const sectionRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const subtitleRef = useRef<HTMLParagraphElement>(null);
  const ctaRef = useRef<HTMLDivElement>(null);
  const screenshotRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoggedIn(!!token && !isTokenExpired(token));
  }, [token]);

  useGSAP(() => {
    if (!sectionRef.current) return;

    const heading = headingRef.current;
    const subtitle = subtitleRef.current;
    const cta = ctaRef.current;
    const screenshot = screenshotRef.current;

    // Split heading text into words
    if (heading) {
      const text = heading.textContent || "";
      heading.innerHTML = text
        .split(" ")
        .map(
          (w) =>
            `<span class="word inline-block">${w}&nbsp;</span>`
        )
        .join("");
    }

    // Gradient mesh pulse — infinite
    const mesh = sectionRef.current.querySelector(".gradient-mesh");
    if (mesh) {
      gsap.to(mesh, {
        opacity: 0.8,
        duration: 3,
        repeat: -1,
        yoyo: true,
        ease: "sine.inOut",
      });
    }

    // ── Entrance animation (plays immediately on load) ──
    const entranceTl = gsap.timeline({ delay: 0.2 });

    // 1. Title words staggered reveal
    if (heading) {
      entranceTl.from(heading.querySelectorAll(".word"), {
        y: 40,
        opacity: 0,
        stagger: 0.08,
        ease: "back.out(1.7)",
        duration: 0.8,
      });
    }

    // 2. Subtitle fade in
    if (subtitle) {
      entranceTl.from(
        subtitle,
        { y: 20, opacity: 0, duration: 0.6, ease: "power2.out" },
        "-=0.3"
      );
    }

    // 3. CTA buttons scale in
    if (cta) {
      entranceTl.from(
        cta.children,
        {
          scale: 0.8,
          opacity: 0,
          ease: "back.out(2)",
          stagger: 0.15,
          duration: 0.6,
        },
        "-=0.2"
      );
    }

    // 4. Screenshot entrance
    if (screenshot) {
      entranceTl.from(
        screenshot,
        {
          scale: 0.85,
          rotateX: -15,
          opacity: 0,
          ease: "power3.out",
          duration: 1,
        },
        "-=0.4"
      );
    }

    // ── Scroll-linked parallax on screenshot (lightweight) ──
    if (screenshot) {
      gsap.to(screenshot, {
        rotateX: 8,
        scale: 1.05,
        y: -30,
        ease: "none",
        scrollTrigger: {
          trigger: sectionRef.current,
          start: "top top",
          end: "bottom top",
          scrub: true,
        },
      });
    }
  }, { scope: sectionRef });

  return (
    <section ref={sectionRef} className="relative" style={{ overflowX: "clip", overflowY: "visible" }}>
      {/* Atmospheric gradient mesh */}
      <div className="gradient-mesh absolute inset-0 -z-10 h-[85%] overflow-hidden">
        <div className="absolute left-1/2 top-0 h-[800px] w-[1200px] -translate-x-1/2 -translate-y-1/4 rounded-full bg-gradient-to-br from-primary/20 via-primary/10 to-transparent blur-3xl" />
        <div className="absolute right-0 top-1/3 h-[400px] w-[600px] rounded-full bg-gradient-to-l from-primary/5 to-transparent blur-2xl" />
      </div>

      {/* Hero heading + CTA */}
      <div className="mx-auto max-w-4xl px-6 pb-12 pt-24 text-center lg:pt-32">
        <h1
          ref={headingRef}
          className="font-display text-4xl font-bold leading-[1.1] tracking-tight text-ink sm:text-5xl lg:text-6xl"
          style={{ letterSpacing: "-1.5px" }}
        >
          Stop losing weeks to literature reviews.
        </h1>

        <p
          ref={subtitleRef}
          className="mx-auto mt-4 max-w-2xl text-base leading-relaxed text-body sm:text-lg"
        >
          Search across academic sources, build a structured evidence matrix,
          detect research gaps, and export citation-safe reviews — all in one
          workspace.
        </p>

        <div
          ref={ctaRef}
          className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row"
        >
          <MagneticButton
            onClick={() => router.push(loggedIn ? "/dashboard" : "/login")}
            className="inline-flex h-11 cursor-pointer items-center justify-center rounded-full bg-primary px-7 text-sm font-semibold text-on-primary transition-colors hover:bg-primary-deep"
          >
            {loggedIn ? "Go to Dashboard" : "Start for free"}
          </MagneticButton>
          <a
            href="#workflow"
            className="inline-flex h-11 items-center justify-center rounded-full border border-hairline-strong bg-surface-card px-7 text-sm font-semibold text-ink transition-colors hover:bg-surface-bone"
          >
            See how it works
          </a>
        </div>
      </div>

      {/* Screenshot with 3D parallax */}
      <div
        ref={screenshotRef}
        className="relative z-30 mx-auto mb-0 w-full max-w-6xl px-4 pb-0 lg:-mb-44"
        style={{
          perspective: "1000px",
          transformStyle: "preserve-3d",
          backfaceVisibility: "hidden",
          willChange: "transform",
        }}
      >
        <img
          src="/hero-screenshot.png"
          alt="AI Literature Review Assistant"
          className="mx-auto h-auto w-full rounded-2xl shadow-2xl"
        />
      </div>
    </section>
  );
}
