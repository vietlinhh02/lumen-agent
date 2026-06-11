# Landing Page GSAP Cinematic Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Lumen landing page from static CSS animations to a full cinematic GSAP experience with pinned sections, text reveal, custom cursor, magnetic buttons, and scroll-triggered animations.

**Architecture:** Install GSAP 3 + @gsap/react. Create 3 new reusable components (CustomCursor, TextReveal, MagneticButton). Rewrite 5 existing section components to use GSAP ScrollTrigger with pinned sections. Update Navbar and Footer with subtle GSAP enhancements. Register GSAP plugins in page.tsx.

**Tech Stack:** React 19, Next.js 16, GSAP 3, @gsap/react, ScrollTrigger, Tailwind v4

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `frontend/package.json` | Modify | Add `gsap`, `@gsap/react` |
| `frontend/components/landing/TextReveal.tsx` | Create | Reusable text splitter + GSAP stagger animation |
| `frontend/components/landing/MagneticButton.tsx` | Create | Cursor-tracking magnetic hover button |
| `frontend/components/landing/CustomCursor.tsx` | Create | Dual-ring custom cursor with quickTo() |
| `frontend/app/globals.css` | Modify | Add cursor styles, nav-scrolled, word styles |
| `frontend/app/page.tsx` | Modify | Register GSAP plugins, add CustomCursor |
| `frontend/components/landing/Navbar.tsx` | Modify | Add scroll-aware GSAP background |
| `frontend/components/landing/Hero.tsx` | Rewrite | GSAP pinned hero with text reveal + 3D parallax |
| `frontend/components/landing/WorkflowSteps.tsx` | Rewrite | GSAP pinned steps with sequential card animation |
| `frontend/components/landing/PainPoints.tsx` | Rewrite | GSAP scroll-triggered counter animations |
| `frontend/components/landing/Features.tsx` | Rewrite | GSAP scroll-triggered with image parallax |
| `frontend/components/landing/CtaBand.tsx` | Rewrite | GSAP pinned CTA with gradient pulse |

---

### Task 1: Install GSAP Dependencies

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install gsap and @gsap/react**

```bash
cd frontend && npm install gsap @gsap/react
```

- [ ] **Step 2: Verify installation**

```bash
cd frontend && node -e "const gsap = require('gsap'); console.log('GSAP version:', gsap.version)"
```

Expected: `GSAP version: 3.x.x`

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "deps: add gsap and @gsap/react for landing page animations"
```

---

### Task 2: Add CSS for Custom Cursor and GSAP States

**Files:**
- Modify: `frontend/app/globals.css`

- [ ] **Step 1: Append cursor and GSAP CSS to globals.css**

Add after the existing `@layer base` block (after line 308):

```css
/* ── Custom Cursor ── */
.cursor-outer {
  position: fixed;
  top: 0;
  left: 0;
  width: 40px;
  height: 40px;
  border: 2px solid var(--ink);
  border-radius: 50%;
  pointer-events: none;
  z-index: 9999;
  mix-blend-mode: difference;
  transform: translate(-50%, -50%);
}

.cursor-inner {
  position: fixed;
  top: 0;
  left: 0;
  width: 8px;
  height: 8px;
  background: var(--ink);
  border-radius: 50%;
  pointer-events: none;
  z-index: 9999;
  mix-blend-mode: difference;
  transform: translate(-50%, -50%);
}

@media (min-width: 768px) {
  body.gsap-cursor-active {
    cursor: none;
  }
  body.gsap-cursor-active a,
  body.gsap-cursor-active button {
    cursor: none;
  }
}

/* ── Navbar scroll state ── */
.nav-scrolled {
  background: rgba(249, 247, 243, 0.9) !important;
  border-bottom: 1px solid var(--hairline) !important;
}

/* ── Text reveal word spans ── */
.word {
  display: inline-block;
  will-change: transform, opacity;
}

/* ── Step card active highlight ── */
.step-card-active {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 1px var(--primary);
}
```

- [ ] **Step 2: Verify CSS is valid**

Check that the file still parses correctly by reading the new section.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/globals.css
git commit -m "css: add cursor, nav-scrolled, and text reveal styles for GSAP"
```

---

### Task 3: Create TextReveal Component

**Files:**
- Create: `frontend/components/landing/TextReveal.tsx`

- [ ] **Step 1: Create TextReveal component**

```tsx
"use client";

import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

interface TextRevealProps {
  children: string;
  as?: "h1" | "h2" | "h3" | "p";
  className?: string;
  stagger?: number;
  y?: number;
  ease?: string;
  start?: string;
}

export function TextReveal({
  children,
  as: Tag = "h2",
  className = "",
  stagger = 0.06,
  y = 30,
  ease = "back.out(1.7)",
  start = "top 85%",
}: TextRevealProps) {
  const ref = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!ref.current) return;
    const words = ref.current.querySelectorAll(".word");
    if (!words.length) return;

    gsap.from(words, {
      y,
      opacity: 0,
      rotationX: -10,
      stagger,
      ease,
      scrollTrigger: {
        trigger: ref.current,
        start,
        toggleActions: "play none none none",
      },
    });
  }, { scope: ref });

  const words = children.split(" ").map((w, i) => (
    <span
      key={i}
      className="word inline-block"
      style={{ perspective: 400 }}
    >
      {w}&nbsp;
    </span>
  ));

  return (
    <Tag ref={ref} className={className}>
      {words}
    </Tag>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -i "TextReveal" || echo "No errors in TextReveal"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/landing/TextReveal.tsx
git commit -m "feat: add TextReveal component for GSAP text animations"
```

---

### Task 4: Create MagneticButton Component

**Files:**
- Create: `frontend/components/landing/MagneticButton.tsx`

- [ ] **Step 1: Create MagneticButton component**

```tsx
"use client";

import { useRef, type ButtonHTMLAttributes } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

interface MagneticButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
  strength?: number;
}

export function MagneticButton({
  children,
  className = "",
  strength = 0.3,
  ...props
}: MagneticButtonProps) {
  const ref = useRef<HTMLButtonElement>(null);

  const { contextSafe } = useGSAP({ scope: ref });

  const onMouseMove = contextSafe((e: React.MouseEvent) => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    gsap.to(ref.current, {
      x: x * strength,
      y: y * strength,
      duration: 0.3,
      ease: "power2.out",
    });
  });

  const onMouseLeave = contextSafe(() => {
    if (!ref.current) return;
    gsap.to(ref.current, {
      x: 0,
      y: 0,
      duration: 0.5,
      ease: "elastic.out(1, 0.5)",
    });
  });

  return (
    <button
      ref={ref}
      className={className}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
      {...props}
    >
      {children}
    </button>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -i "MagneticButton" || echo "No errors in MagneticButton"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/landing/MagneticButton.tsx
git commit -m "feat: add MagneticButton component for cursor-tracking hover"
```

---

### Task 5: Create CustomCursor Component

**Files:**
- Create: `frontend/components/landing/CustomCursor.tsx`

- [ ] **Step 1: Create CustomCursor component**

```tsx
"use client";

import { useRef, useEffect, useState } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

export function CustomCursor() {
  const outerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const [isMobile, setIsMobile] = useState(true);

  useEffect(() => {
    setIsMobile(window.innerWidth < 768);
    const onResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useGSAP(() => {
    if (isMobile || !outerRef.current || !innerRef.current) return;

    const outer = outerRef.current;
    const inner = innerRef.current;

    const xTo = gsap.quickTo(outer, "x", {
      duration: 0.4,
      ease: "power3",
    });
    const yTo = gsap.quickTo(outer, "y", {
      duration: 0.4,
      ease: "power3",
    });
    const xInner = gsap.quickTo(inner, "x", {
      duration: 0.15,
      ease: "power2",
    });
    const yInner = gsap.quickTo(inner, "y", {
      duration: 0.15,
      ease: "power2",
    });

    const onMouseMove = (e: MouseEvent) => {
      xTo(e.clientX);
      yTo(e.clientY);
      xInner(e.clientX);
      yInner(e.clientY);
    };

    const onMouseEnterInteractive = () => {
      gsap.to(outer, { scale: 2, opacity: 0.5, duration: 0.3 });
    };
    const onMouseLeaveInteractive = () => {
      gsap.to(outer, { scale: 1, opacity: 1, duration: 0.3 });
    };

    window.addEventListener("mousemove", onMouseMove);

    const interactives = document.querySelectorAll("a, button, [data-magnetic]");
    interactives.forEach((el) => {
      el.addEventListener("mouseenter", onMouseEnterInteractive);
      el.addEventListener("mouseleave", onMouseLeaveInteractive);
    });

    document.body.classList.add("gsap-cursor-active");

    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      document.body.classList.remove("gsap-cursor-active");
      interactives.forEach((el) => {
        el.removeEventListener("mouseenter", onMouseEnterInteractive);
        el.removeEventListener("mouseleave", onMouseLeaveInteractive);
      });
    };
  }, [isMobile]);

  if (isMobile) return null;

  return (
    <>
      <div ref={outerRef} className="cursor-outer" />
      <div ref={innerRef} className="cursor-inner" />
    </>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -i "CustomCursor" || echo "No errors in CustomCursor"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/landing/CustomCursor.tsx
git commit -m "feat: add CustomCursor component with quickTo() smooth following"
```

---

### Task 6: Register GSAP Plugins and Add CustomCursor to page.tsx

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Rewrite page.tsx with GSAP registration**

```tsx
"use client";

import { useEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

import { Navbar } from "@/components/landing/Navbar";
import { Hero } from "@/components/landing/Hero";
import { WorkflowSteps } from "@/components/landing/WorkflowSteps";
import { PainPoints } from "@/components/landing/PainPoints";
import { Features } from "@/components/landing/Features";
import { CtaBand } from "@/components/landing/CtaBand";
import { Footer } from "@/components/landing/Footer";
import { CustomCursor } from "@/components/landing/CustomCursor";

gsap.registerPlugin(ScrollTrigger, useGSAP);

export default function LandingPage() {
  useGSAP(() => {
    ScrollTrigger.refresh();
  });

  return (
    <div className="min-h-screen bg-canvas">
      <CustomCursor />
      <Navbar />
      <Hero />
      <WorkflowSteps />
      <PainPoints />
      <Features />
      <CtaBand />
      <Footer />
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat: register GSAP plugins and add CustomCursor to landing page"
```

---

### Task 7: Rewrite Navbar with Scroll-Aware GSAP

**Files:**
- Modify: `frontend/components/landing/Navbar.tsx`

- [ ] **Step 1: Rewrite Navbar with GSAP scroll-aware background**

```tsx
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { List, X } from "@phosphor-icons/react";
import { isTokenExpired, TOKEN_KEY } from "@/lib/jwt";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

const navLinks = [
  { label: "Workflow", href: "#workflow" },
  { label: "Features", href: "#features" },
  { label: "Why Lumen", href: "#pain-points" },
];

export function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const router = useRouter();
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    setLoggedIn(!!token && !isTokenExpired(token));
  }, []);

  useGSAP(() => {
    if (!navRef.current) return;

    const links = navRef.current.querySelectorAll(".nav-link");
    gsap.from(links, {
      y: -10,
      opacity: 0,
      stagger: 0.08,
      duration: 0.6,
      ease: "power2.out",
      delay: 0.2,
    });

    gsap.to(navRef.current, {
      scrollTrigger: {
        trigger: navRef.current,
        start: "top -80",
        onEnter: () => navRef.current?.classList.add("nav-scrolled"),
        onLeaveBack: () => navRef.current?.classList.remove("nav-scrolled"),
      },
    });
  }, { scope: navRef });

  function handleAuthClick() {
    router.push("/login");
  }

  function handleDashboardClick() {
    router.push("/dashboard");
  }

  return (
    <nav
      ref={navRef}
      className="sticky top-0 z-50 border-b border-transparent bg-canvas/80 backdrop-blur-xl transition-colors"
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2">
          <span
            className="font-display text-xl font-bold text-ink"
            style={{ letterSpacing: "-0.5px" }}
          >
            Lumen
          </span>
        </Link>

        <div className="hidden items-center gap-8 md:flex">
          {navLinks.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="nav-link text-sm font-medium text-charcoal transition-colors hover:text-ink"
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

        <button
          className="flex h-10 w-10 items-center justify-center rounded-full text-ink md:hidden"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle menu"
        >
          {mobileOpen ? <X size={24} /> : <List size={24} />}
        </button>
      </div>

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
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -i "Navbar" || echo "No errors in Navbar"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/landing/Navbar.tsx
git commit -m "feat: add scroll-aware GSAP animation to Navbar"
```

---

### Task 8: Rewrite Hero with Pinned GSAP + Text Reveal + 3D Parallax

**Files:**
- Modify: `frontend/components/landing/Hero.tsx`

- [ ] **Step 1: Rewrite Hero with GSAP pinned timeline**

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { isTokenExpired, TOKEN_KEY } from "@/lib/jwt";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { MagneticButton } from "./MagneticButton";

export function Hero() {
  const router = useRouter();
  const [loggedIn, setLoggedIn] = useState(false);
  const sectionRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const subtitleRef = useRef<HTMLParagraphElement>(null);
  const ctaRef = useRef<HTMLDivElement>(null);
  const screenshotRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    setLoggedIn(!!token && !isTokenExpired(token));
  }, []);

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
            `<span class="word inline-block" style="perspective:400px">${w}&nbsp;</span>`
        )
        .join("");
    }

    // Gradient mesh pulse
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

    // Create pinned timeline
    const tl = gsap.timeline({
      scrollTrigger: {
        trigger: sectionRef.current,
        start: "top top",
        end: "+=200%",
        pin: true,
        scrub: 0.5,
      },
    });

    // 1. Title words staggered reveal
    if (heading) {
      tl.from(heading.querySelectorAll(".word"), {
        y: 40,
        opacity: 0,
        rotationX: -15,
        stagger: 0.08,
        ease: "back.out(1.7)",
      });
    }

    // 2. Subtitle fade in
    if (subtitle) {
      tl.from(
        subtitle,
        { y: 20, opacity: 0, duration: 0.6, ease: "power2.out" },
        "-=0.3"
      );
    }

    // 3. CTA buttons scale in
    if (cta) {
      tl.from(
        cta.children,
        {
          scale: 0.8,
          opacity: 0,
          ease: "back.out(2)",
          stagger: 0.15,
        },
        "-=0.2"
      );
    }

    // 4. Screenshot entrance
    if (screenshot) {
      tl.from(
        screenshot,
        {
          scale: 0.85,
          rotateX: -15,
          opacity: 0,
          ease: "power3.out",
        },
        "-=0.4"
      );

      // 5. Scroll-linked parallax on screenshot
      tl.to(screenshot, {
        rotateX: 8,
        scale: 1.08,
        y: -40,
        ease: "none",
      });
    }
  }, { scope: sectionRef });

  return (
    <section ref={sectionRef} className="relative overflow-visible">
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
        className="relative z-10 mx-auto mb-0 w-full max-w-6xl overflow-visible px-4 pb-0 lg:-mb-44"
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
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -i "Hero" || echo "No errors in Hero"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/landing/Hero.tsx
git commit -m "feat: rewrite Hero with GSAP pinned timeline, text reveal, 3D parallax"
```

---

### Task 9: Rewrite WorkflowSteps with Pinned GSAP + Sequential Card Animation

**Files:**
- Modify: `frontend/components/landing/WorkflowSteps.tsx`

- [ ] **Step 1: Rewrite WorkflowSteps with GSAP pinned timeline**

```tsx
"use client";

import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

const steps = [
  {
    number: "01",
    title: "Search Papers",
    description:
      "Query across Semantic Scholar, OpenAlex, arXiv, Exa, and Firecrawl in one search. Language-bias audit included.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.35-4.35" />
      </svg>
    ),
  },
  {
    number: "02",
    title: "Save & Screen",
    description:
      "Select relevant papers into your project corpus. Deduplication happens automatically across sources.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
        <polyline points="17 21 17 13 7 13 7 21" />
        <polyline points="7 3 7 8 15 8" />
      </svg>
    ),
  },
  {
    number: "03",
    title: "Generate Matrix",
    description:
      "AI extracts structured fields: method, dataset, key result, limitation. Edit any cell — your corrections are saved.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <path d="M3 9h18" />
        <path d="M3 15h18" />
        <path d="M9 3v18" />
        <path d="M15 3v18" />
      </svg>
    ),
  },
  {
    number: "04",
    title: "Explore Knowledge Map",
    description:
      "Visualize connections between papers, methods, datasets, and limitations in an interactive force-directed graph.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="3" />
        <circle cx="4" cy="6" r="2" />
        <circle cx="20" cy="6" r="2" />
        <circle cx="4" cy="18" r="2" />
        <circle cx="20" cy="18" r="2" />
        <path d="m6.5 7.5 3 3" />
        <path d="m17.5 7.5-3 3" />
        <path d="m6.5 16.5 3-3" />
        <path d="m17.5 16.5-3-3" />
      </svg>
    ),
  },
  {
    number: "05",
    title: "Detect Gaps",
    description:
      "Evidence-based research gap detection. Every gap references specific saved papers — no generic future work.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 2v20" />
        <path d="M2 12h20" />
        <circle cx="12" cy="12" r="10" />
        <path d="M12 8v4" />
        <circle cx="12" cy="16" r="0.5" fill="currentColor" />
      </svg>
    ),
  },
  {
    number: "06",
    title: "Export Review",
    description:
      "Generate a citation-safe literature review. The backend validates every citation ID before export. No hallucinated references.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <path d="M9 15l2 2 4-4" />
      </svg>
    ),
  },
];

export function WorkflowSteps() {
  const sectionRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!sectionRef.current) return;

    const heading = headingRef.current;
    const cards = sectionRef.current.querySelectorAll(".step-card");
    const icons = sectionRef.current.querySelectorAll(".step-icon");

    // Split heading text
    if (heading) {
      const h2 = heading.querySelector("h2");
      if (h2) {
        const text = h2.textContent || "";
        h2.innerHTML = text
          .split(" ")
          .map(
            (w) =>
              `<span class="word inline-block" style="perspective:400px">${w}&nbsp;</span>`
          )
          .join("");
      }
    }

    const tl = gsap.timeline({
      scrollTrigger: {
        trigger: sectionRef.current,
        start: "top top",
        end: "+=150%",
        pin: true,
        scrub: 0.3,
      },
    });

    // 1. Heading text reveal
    if (heading) {
      tl.from(heading.querySelectorAll(".word"), {
        y: 30,
        opacity: 0,
        stagger: 0.06,
        ease: "back.out(1.7)",
      });
    }

    // 2. Cards staggered entrance
    tl.from(
      cards,
      {
        y: 60,
        opacity: 0,
        scale: 0.95,
        stagger: 0.12,
        ease: "power2.out",
      },
      "-=0.3"
    );

    // 3. Icons rotate in
    tl.from(
      icons,
      {
        rotation: -90,
        scale: 0,
        stagger: 0.1,
        ease: "back.out(2)",
      },
      "-=0.8"
    );
  }, { scope: sectionRef });

  return (
    <section
      ref={sectionRef}
      id="workflow"
      className="bg-surface-bone pb-24 pt-36 lg:pb-32 lg:pt-48"
    >
      <div className="mx-auto max-w-7xl px-6">
        <div ref={headingRef} className="mb-16 max-w-2xl">
          <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-primary">
            How it works
          </p>
          <h2
            className="font-display text-4xl font-bold leading-[1.0] tracking-tight text-ink sm:text-5xl"
            style={{ letterSpacing: "-1px" }}
          >
            From search to export in six steps.
          </h2>
          <p className="mt-4 text-lg text-body">
            Every step produces a visible, editable artifact. No black boxes.
            No hidden AI decisions.
          </p>
        </div>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {steps.map((step) => (
            <div
              key={step.number}
              className="step-card group relative rounded-xl border border-hairline bg-surface-card p-6 transition-all hover:border-hairline-strong hover:shadow-lg"
            >
              <div className="mb-4 flex items-center gap-3">
                <div className="step-icon flex h-10 w-10 items-center justify-center rounded-full bg-canvas text-charcoal transition-colors group-hover:bg-primary group-hover:text-on-primary">
                  {step.icon}
                </div>
                <span className="text-xs font-bold text-ash">
                  {step.number}
                </span>
              </div>
              <h3 className="mb-2 text-lg font-semibold text-ink">
                {step.title}
              </h3>
              <p className="text-sm leading-relaxed text-charcoal">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -i "WorkflowSteps" || echo "No errors in WorkflowSteps"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/landing/WorkflowSteps.tsx
git commit -m "feat: rewrite WorkflowSteps with GSAP pinned sequential animation"
```

---

### Task 10: Rewrite PainPoints with Scroll-Triggered Counter Animations

**Files:**
- Modify: `frontend/components/landing/PainPoints.tsx`

- [ ] **Step 1: Rewrite PainPoints with GSAP scroll-triggered counters**

```tsx
"use client";

import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

const stats = [
  {
    value: 72,
    suffix: "%",
    label: "of AI-generated citations are fabricated",
    source: "Athaluri et al., 2024",
  },
  {
    value: 1000,
    suffix: "+",
    label: "person-hours for a full systematic review",
    source: "Systematic Review Guide, 2026",
  },
  {
    value: 5,
    suffix: "+",
    label: "disconnected tools cobbled together",
    source: "ResearchGold, 2026",
  },
  {
    value: 288,
    suffix: " years",
    label: "to read 105k papers from one search",
    source: "LessWrong",
  },
];

export function PainPoints() {
  const sectionRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!sectionRef.current) return;

    const heading = headingRef.current;

    // Split heading text
    if (heading) {
      const h2 = heading.querySelector("h2");
      if (h2) {
        const text = h2.textContent || "";
        h2.innerHTML = text
          .split(" ")
          .map(
            (w) =>
              `<span class="word inline-block" style="perspective:400px">${w}&nbsp;</span>`
          )
          .join("");
      }
    }

    // Heading text reveal
    if (heading) {
      gsap.from(heading.querySelectorAll(".word"), {
        y: 30,
        opacity: 0,
        stagger: 0.06,
        ease: "back.out(1.7)",
        scrollTrigger: {
          trigger: heading,
          start: "top 85%",
        },
      });
    }

    // Counter animations for stats
    const statValues = sectionRef.current.querySelectorAll(".stat-value");
    statValues.forEach((el) => {
      const target = parseInt(el.getAttribute("data-target") || "0", 10);
      const counter = { value: 0 };
      gsap.to(counter, {
        value: target,
        duration: 2,
        ease: "power1.inOut",
        scrollTrigger: {
          trigger: el,
          start: "top 85%",
        },
        onUpdate: () => {
          el.textContent = Math.round(counter.value).toString();
        },
      });
    });

    // Trust chain pills reveal
    const pills = sectionRef.current.querySelectorAll(".trust-pill");
    const arrows = sectionRef.current.querySelectorAll(".trust-arrow");

    gsap.from(pills, {
      x: -20,
      opacity: 0,
      stagger: 0.1,
      ease: "power2.out",
      scrollTrigger: {
        trigger: ".trust-chain",
        start: "top 85%",
      },
    });

    gsap.from(arrows, {
      scale: 0,
      opacity: 0,
      stagger: 0.1,
      ease: "back.out(2)",
      scrollTrigger: {
        trigger: ".trust-chain",
        start: "top 85%",
      },
      delay: 0.3,
    });
  }, { scope: sectionRef });

  return (
    <section
      ref={sectionRef}
      id="pain-points"
      className="bg-surface-dark py-24 lg:py-32"
    >
      <div className="mx-auto max-w-7xl px-6">
        <div ref={headingRef} className="mb-16 max-w-2xl">
          <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-primary">
            The problem
          </p>
          <h2
            className="font-display text-4xl font-bold leading-[1.0] text-on-dark sm:text-5xl"
            style={{ letterSpacing: "-1px" }}
          >
            Literature reviews are broken. Here&rsquo;s why.
          </h2>
        </div>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {stats.map((stat, i) => (
            <div
              key={i}
              className="rounded-xl border border-[rgba(255,255,255,0.1)] p-6"
            >
              <p
                className="stat-value font-display text-4xl font-bold text-primary"
                style={{ letterSpacing: "-1px" }}
                data-target={stat.value}
              >
                0
              </p>
              <p className="mt-2 text-sm leading-relaxed text-on-dark">
                {stat.suffix && (
                  <span className="stat-suffix">{stat.suffix}</span>
                )}{" "}
                {stat.label}
              </p>
              <p className="mt-3 text-xs text-on-dark-mute">{stat.source}</p>
            </div>
          ))}
        </div>

        {/* Trust chain */}
        <div className="trust-chain mt-16 rounded-xl border border-[rgba(255,255,255,0.1)] p-8">
          <p className="mb-6 text-sm font-semibold uppercase tracking-wider text-primary">
            The trust chain
          </p>
          <div className="flex flex-wrap items-center gap-3 text-sm text-on-dark lg:gap-4">
            {[
              "Can't find papers",
              "Don't trust sources",
              "Can't organize",
              "Can't synthesize",
              "AI invents citations",
              "Can't verify",
              "Don't trust output",
            ].map((step, i, arr) => (
              <span key={i} className="flex items-center gap-3">
                <span className="trust-pill rounded-full bg-[rgba(255,255,255,0.08)] px-3 py-1.5">
                  {step}
                </span>
                {i < arr.length - 1 && (
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    className="trust-arrow hidden text-ash sm:block"
                  >
                    <path d="M5 12h14" />
                    <path d="m12 5 7 7-7 7" />
                  </svg>
                )}
              </span>
            ))}
          </div>
          <p className="mt-6 max-w-2xl text-sm leading-relaxed text-on-dark-mute">
            Lumen breaks this chain by enforcing evidence at every step. Real
            papers from real sources. Structured matrix from saved papers.
            Gaps backed by evidence. Citations validated against your project
            database before export.
          </p>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -i "PainPoints" || echo "No errors in PainPoints"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/landing/PainPoints.tsx
git commit -m "feat: rewrite PainPoints with GSAP counter animations and trust chain reveal"
```

---

### Task 11: Rewrite Features with Scroll-Triggered Image Parallax

**Files:**
- Modify: `frontend/components/landing/Features.tsx`

- [ ] **Step 1: Rewrite Features with GSAP scroll-triggered parallax**

```tsx
"use client";

import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

const features = [
  {
    title: "Multi-Source Search",
    description:
      "Search across Semantic Scholar, OpenAlex, arXiv, Exa, and Firecrawl in one query. Partial results shown when one source fails.",
    image: "https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=600&q=80&auto=format",
    imageAlt: "Library with rows of bookshelves",
    tags: ["5 sources", "Language audit", "Deduplication"],
  },
  {
    title: "Literature Matrix",
    description:
      "AI extracts method, dataset, key result, limitation, and relevance for each paper. Edit any cell — your corrections persist.",
    image: "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=600&q=80&auto=format",
    imageAlt: "Notes and data spread across a desk",
    tags: ["Structured data", "Editable", "Confidence scores"],
  },
  {
    title: "Citation Guardrail",
    description:
      "The backend validates every citation ID against your saved project papers. Invalid references are rejected before export. No hallucinated bibliography.",
    image: "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=600&q=80&auto=format",
    imageAlt: "Open books stacked on a desk",
    tags: ["Backend validation", "DB-backed", "Export-ready"],
  },
];

export function Features() {
  const sectionRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!sectionRef.current) return;

    const heading = headingRef.current;

    // Split heading text
    if (heading) {
      const h2 = heading.querySelector("h2");
      if (h2) {
        const text = h2.textContent || "";
        h2.innerHTML = text
          .split(" ")
          .map(
            (w) =>
              `<span class="word inline-block" style="perspective:400px">${w}&nbsp;</span>`
          )
          .join("");
      }
    }

    // Heading text reveal
    if (heading) {
      gsap.from(heading.querySelectorAll(".word"), {
        y: 30,
        opacity: 0,
        stagger: 0.06,
        ease: "back.out(1.7)",
        scrollTrigger: {
          trigger: heading,
          start: "top 85%",
        },
      });
    }

    // Feature cards staggered entrance
    const cards = sectionRef.current.querySelectorAll(".feature-card");
    gsap.from(cards, {
      y: 50,
      opacity: 0,
      stagger: 0.15,
      ease: "power2.out",
      scrollTrigger: {
        trigger: cards[0],
        start: "top 85%",
      },
    });

    // Image parallax inside each card
    const images = sectionRef.current.querySelectorAll(".feature-img");
    images.forEach((img) => {
      gsap.to(img, {
        y: -20,
        ease: "none",
        scrollTrigger: {
          trigger: img.closest(".feature-card"),
          start: "top bottom",
          end: "bottom top",
          scrub: true,
        },
      });
    });

    // Tags staggered fade-in within each card
    cards.forEach((card) => {
      const tags = card.querySelectorAll(".feature-tag");
      gsap.from(tags, {
        y: 10,
        opacity: 0,
        stagger: 0.08,
        ease: "power2.out",
        scrollTrigger: {
          trigger: card,
          start: "top 80%",
        },
      });
    });

    // Secondary feature cards
    const secondaryCards = sectionRef.current.querySelectorAll(".secondary-card");
    gsap.from(secondaryCards, {
      y: 30,
      opacity: 0,
      stagger: 0.1,
      ease: "power2.out",
      scrollTrigger: {
        trigger: secondaryCards[0],
        start: "top 90%",
      },
    });
  }, { scope: sectionRef });

  return (
    <section ref={sectionRef} id="features" className="py-24 lg:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <div ref={headingRef} className="mb-16 max-w-2xl">
          <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-primary">
            Core capabilities
          </p>
          <h2
            className="font-display text-4xl font-bold leading-[1.0] tracking-tight text-ink sm:text-5xl"
            style={{ letterSpacing: "-1px" }}
          >
            Everything you need. Nothing you don&rsquo;t.
          </h2>
          <p className="mt-4 text-lg text-body">
            Eight features, zero fluff. Every capability supports the evidence
            chain from search to export.
          </p>
        </div>

        <div className="grid gap-8 lg:grid-cols-3">
          {features.map((feature, i) => (
            <div
              key={i}
              className="feature-card group overflow-hidden rounded-xl border border-hairline bg-surface-card transition-all hover:border-hairline-strong hover:shadow-lg"
            >
              <div className="relative h-48 overflow-hidden">
                <img
                  src={feature.image}
                  alt={feature.imageAlt}
                  className="feature-img h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-surface-dark/40 to-transparent" />
              </div>
              <div className="p-6">
                <h3 className="mb-2 text-lg font-semibold text-ink">
                  {feature.title}
                </h3>
                <p className="mb-4 text-sm leading-relaxed text-charcoal">
                  {feature.description}
                </p>
                <div className="flex flex-wrap gap-2">
                  {feature.tags.map((tag) => (
                    <span
                      key={tag}
                      className="feature-tag rounded-full border border-hairline bg-canvas px-3 py-1 text-xs font-medium text-charcoal"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Secondary features grid */}
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {[
            {
              title: "Knowledge Map",
              desc: "Interactive graph of papers, methods, datasets.",
            },
            {
              title: "Research Gaps",
              desc: "Evidence-backed gap detection with paper references.",
            },
            {
              title: "Conflict Detection",
              desc: "Flag opposing findings across studies.",
            },
            {
              title: "PDF Ingestion",
              desc: "Download, extract, and chunk full-text PDFs.",
            },
            {
              title: "Agent Audit",
              desc: "Full LangGraph workflow transparency.",
            },
          ].map((item, i) => (
            <div
              key={i}
              className="secondary-card rounded-xl border border-hairline bg-surface-card p-4"
            >
              <h4 className="mb-1 text-sm font-semibold text-ink">
                {item.title}
              </h4>
              <p className="text-xs leading-relaxed text-charcoal">
                {item.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -i "Features" || echo "No errors in Features"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/landing/Features.tsx
git commit -m "feat: rewrite Features with GSAP scroll-triggered parallax and stagger"
```

---

### Task 12: Rewrite CtaBand with Pinned GSAP + Gradient Pulse

**Files:**
- Modify: `frontend/components/landing/CtaBand.tsx`

- [ ] **Step 1: Rewrite CtaBand with GSAP pinned timeline**

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { isTokenExpired, TOKEN_KEY } from "@/lib/jwt";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { MagneticButton } from "./MagneticButton";

export function CtaBand() {
  const router = useRouter();
  const [loggedIn, setLoggedIn] = useState(false);
  const sectionRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    setLoggedIn(!!token && !isTokenExpired(token));
  }, []);

  useGSAP(() => {
    if (!sectionRef.current || !headingRef.current) return;

    // Split heading text
    const h2 = headingRef.current;
    const text = h2.textContent || "";
    h2.innerHTML = text
      .split(" ")
      .map(
        (w) =>
          `<span class="word inline-block" style="perspective:400px">${w}&nbsp;</span>`
      )
      .join("");

    // Gradient pulse
    const gradient = sectionRef.current.querySelector(".cta-gradient");
    if (gradient) {
      gsap.to(gradient, {
        scale: 1.1,
        opacity: 0.7,
        duration: 3,
        repeat: -1,
        yoyo: true,
        ease: "sine.inOut",
      });
    }

    // Floating circles
    const circles = sectionRef.current.querySelectorAll(".floating-circle");
    circles.forEach((circle, i) => {
      gsap.to(circle, {
        y: `random(-30, 30)`,
        x: `random(-20, 20)`,
        duration: `random(3, 5)`,
        repeat: -1,
        yoyo: true,
        ease: "sine.inOut",
        delay: i * 0.5,
      });
    });

    // Pinned timeline
    const tl = gsap.timeline({
      scrollTrigger: {
        trigger: sectionRef.current,
        start: "top top",
        end: "+=100%",
        pin: true,
        scrub: 0.3,
      },
    });

    // Heading reveal with scale
    tl.from(h2.querySelectorAll(".word"), {
      scale: 0.9,
      opacity: 0,
      stagger: 0.08,
      ease: "back.out(1.7)",
    });

    // CTA buttons
    const ctaButtons = sectionRef.current.querySelector(".cta-buttons");
    if (ctaButtons) {
      tl.from(
        ctaButtons.children,
        {
          scale: 0.8,
          opacity: 0,
          ease: "back.out(2)",
          stagger: 0.15,
        },
        "-=0.3"
      );
    }
  }, { scope: sectionRef });

  return (
    <section
      ref={sectionRef}
      className="relative overflow-hidden bg-primary py-24 lg:py-32"
    >
      {/* Animated gradient */}
      <div className="cta-gradient absolute left-1/2 top-1/2 h-[600px] w-[800px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-br from-primary-deep/50 to-transparent blur-3xl" />

      {/* Floating circles */}
      <div className="floating-circle absolute left-[10%] top-[20%] h-16 w-16 rounded-full bg-[rgba(255,255,255,0.05)]" />
      <div className="floating-circle absolute right-[15%] top-[30%] h-24 w-24 rounded-full bg-[rgba(255,255,255,0.03)]" />
      <div className="floating-circle absolute left-[20%] bottom-[25%] h-12 w-12 rounded-full bg-[rgba(255,255,255,0.04)]" />
      <div className="floating-circle absolute right-[25%] bottom-[15%] h-20 w-20 rounded-full bg-[rgba(255,255,255,0.06)]" />

      <div className="relative mx-auto max-w-7xl px-6 text-center">
        <h2
          ref={headingRef}
          className="font-display text-4xl font-bold leading-[1.0] text-on-dark sm:text-5xl lg:text-6xl"
          style={{ letterSpacing: "-1.5px" }}
        >
          Ready to illuminate your research?
        </h2>
        <p className="mx-auto mt-6 max-w-md text-lg text-on-dark-mute">
          Build defensible literature reviews with real papers, structured
          evidence, and validated citations.
        </p>
        <div className="cta-buttons mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <MagneticButton
            onClick={() => router.push(loggedIn ? "/dashboard" : "/login")}
            className="inline-flex h-12 cursor-pointer items-center justify-center rounded-full bg-surface-dark px-8 text-base font-semibold text-on-dark transition-colors hover:bg-surface-deep"
          >
            {loggedIn ? "Go to Dashboard" : "Get started free"}
          </MagneticButton>
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
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -i "CtaBand" || echo "No errors in CtaBand"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/landing/CtaBand.tsx
git commit -m "feat: rewrite CtaBand with GSAP pinned timeline, gradient pulse, floating circles"
```

---

### Task 13: Add Subtle GSAP Reveal to Footer

**Files:**
- Modify: `frontend/components/landing/Footer.tsx`

- [ ] **Step 1: Add GSAP scroll-triggered reveal to Footer**

```tsx
"use client";

import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

const footerLinks = {
  Product: [
    { label: "Workflow", href: "#workflow" },
    { label: "Features", href: "#features" },
    { label: "Why Lumen", href: "#pain-points" },
  ],
  Research: [
    { label: "Documentation", href: "#" },
    { label: "API Design", href: "#" },
    { label: "Architecture", href: "#" },
  ],
  Team: [
    { label: "About", href: "#" },
    { label: "GitHub", href: "#" },
    { label: "Contact", href: "#" },
  ],
};

export function Footer() {
  const footerRef = useRef<HTMLElement>(null);

  useGSAP(() => {
    if (!footerRef.current) return;

    const cols = footerRef.current.querySelectorAll(".footer-col");
    gsap.from(cols, {
      y: 30,
      opacity: 0,
      stagger: 0.1,
      ease: "power2.out",
      scrollTrigger: {
        trigger: footerRef.current,
        start: "top 90%",
      },
    });
  }, { scope: footerRef });

  return (
    <footer ref={footerRef} className="bg-surface-deep py-16 lg:py-20">
      <div className="mx-auto max-w-7xl px-6">
        <div className="grid gap-12 lg:grid-cols-4">
          <div className="footer-col">
            <span
              className="font-display text-xl font-bold text-on-dark"
              style={{ letterSpacing: "-0.5px" }}
            >
              Lumen
            </span>
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-on-dark-mute">
              AI-powered literature review assistant. From search to
              citation-safe export, in one workspace.
            </p>
          </div>

          {Object.entries(footerLinks).map(([title, links]) => (
            <div key={title} className="footer-col">
              <h4 className="mb-4 text-sm font-semibold text-on-dark">
                {title}
              </h4>
              <ul className="flex flex-col gap-2.5">
                {links.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      className="text-sm text-on-dark-mute transition-colors hover:text-on-dark"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 border-t border-[rgba(255,255,255,0.1)] pt-8">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
            <p className="text-xs text-on-dark-mute">
              &copy; 2026 Lumen. Built at VinUniversity.
            </p>
            <div className="flex items-center gap-4">
              <span className="rounded-full bg-[rgba(255,255,255,0.08)] px-3 py-1 text-xs text-on-dark-mute">
                FastAPI + Next.js 16
              </span>
              <span className="rounded-full bg-[rgba(255,255,255,0.08)] px-3 py-1 text-xs text-on-dark-mute">
                PostgreSQL + pgvector
              </span>
              <span className="rounded-full bg-[rgba(255,255,255,0.08)] px-3 py-1 text-xs text-on-dark-mute">
                LangGraph
              </span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -i "Footer" || echo "No errors in Footer"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/landing/Footer.tsx
git commit -m "feat: add subtle GSAP scroll-triggered reveal to Footer"
```

---

### Task 14: Final Integration — Verify All Components Work Together

- [ ] **Step 1: Run TypeScript type checker on entire frontend**

```bash
cd frontend && npx tsc --noEmit --pretty
```

Expected: No new errors from GSAP changes (pre-existing errors OK).

- [ ] **Step 2: Run linter**

```bash
cd frontend && npx oxlint src 2>&1 | head -20 || echo "oxlint not configured, skip"
```

- [ ] **Step 3: Start dev server and verify landing page renders**

```bash
cd frontend && npm run dev
```

Manual verification:
- Landing page loads without errors
- Custom cursor appears on desktop
- Hero text reveals on scroll
- WorkflowSteps cards animate in sequence
- PainPoints counters animate
- Features image parallax works
- CtaBand gradient pulses
- Footer fades in
- Mobile: simplified animations, no cursor

- [ ] **Step 4: Final commit with all remaining changes**

```bash
git add -A
git commit -m "feat: complete GSAP cinematic landing page redesign"
```
