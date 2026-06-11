# Landing Page — Full Cinematic GSAP Redesign

## Problem

The current landing page (`frontend/app/page.tsx`) is well-structured with 7 components
(Navbar, Hero, WorkflowSteps, PainPoints, Features, CtaBand, Footer) but is entirely
static. It uses basic CSS keyframe animations (`fade-in`, `slide-up`) and a manual
scroll handler for hero parallax. The page feels flat and lacks the premium, modern feel
expected from a research tool that claims to use cutting-edge AI.

## Goal

Transform the landing page into a full cinematic experience using GSAP — Apple product
page quality. Every section should feel intentional, animated, and premium. The page
should wow visitors within the first 5 seconds.

## Decision

| Area | Choice | Rationale |
|------|--------|-----------|
| Animation library | GSAP 3 (free tier) + @gsap/react | Framework-agnostic, ScrollTrigger built-in, best performance |
| Scroll behavior | Pinned sections (Apple-style) | Each section pins while animation plays, creates immersive experience |
| Hero animation | Animated text reveal + parallax 3D | Most impactful first impression |
| Cursor | Custom cursor + magnetic buttons | Premium feel, sets apart from template sites |
| Text splitting | Custom implementation | Avoids SplitText plugin (paid), same visual result |
| Reduced motion | Not respected (user choice) | Always animate for maximum visual impact |
| Responsive | gsap.matchMedia() for breakpoints | Mobile gets simplified animations, desktop gets full experience |

## Architecture

### Tech Stack

- **GSAP 3** (free): core tween engine
- **@gsap/react**: `useGSAP()` hook for React lifecycle
- **ScrollTrigger** (free): pinned sections, scroll-linked animations
- **Custom TextReveal**: text splitting into spans, staggered animation
- **Custom MagneticButton**: mouse-tracking hover effect
- **Custom CustomCursor**: dual-ring cursor with `quickTo()` smooth following

### GSAP Registration

```tsx
// In page.tsx or a provider
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger, useGSAP);
```

## Section-by-Section Design

### 1. Navbar — Scroll-aware

**Current:** Static sticky nav with backdrop-blur.

**New:** Transparent at top, gains `bg-canvas/90` + border on scroll > 50px.

```tsx
// ScrollTrigger to toggle navbar background
ScrollTrigger.create({
  start: "top -80",
  onEnter: () => navRef.current?.classList.add("nav-scrolled"),
  onLeaveBack: () => navRef.current?.classList.remove("nav-scrolled"),
});
```

- Logo animate in from left (one-time, on page load)
- Nav links staggered fade-in (one-time)
- Mobile: same as current, no GSAP

### 2. Hero — Pinned, Cinematic

**Current:** Static text + scroll-driven parallax on screenshot.

**New:** Full pinned section with sequenced animations.

**Pin:** Hero pins for ~200vh of scroll distance.

**Animation sequence (plays during pin):**

1. **Gradient mesh** — subtle infinite pulse (opacity oscillate 0.6 → 1, duration: 3s, repeat: -1, yoyo: true)
2. **Title text** — split into words, staggered reveal: `y: 40, opacity: 0, rotationX: -15` → `y: 0, opacity: 1, rotationX: 0`, stagger: 0.08s, ease: `back.out(1.7)`
3. **Subtitle** — fade in after title completes: `y: 20, opacity: 0` → `y: 0, opacity: 1`
4. **CTA buttons** — scale in with bounce: `scale: 0.8, opacity: 0` → `scale: 1, opacity: 1`, ease: `back.out(2)`
5. **Screenshot** — entrance: `scale: 0.85, rotateX: -15, opacity: 0` → `scale: 1, rotateX: -5, opacity: 1`, ease: `power3.out`
6. **Scroll-linked parallax** — during pin, screenshot rotateX changes: `-5deg → +8deg`, scale: `1 → 1.08`, translateY: `0 → -40px`

**Implementation:**

```tsx
const heroTl = gsap.timeline({
  scrollTrigger: {
    trigger: heroRef.current,
    start: "top top",
    end: "+=200%",
    pin: true,
    scrub: 0.5,
  },
});

heroTl
  .from(".hero-title .word", {
    y: 40, opacity: 0, rotationX: -15,
    stagger: 0.08, ease: "back.out(1.7)",
  })
  .from(".hero-subtitle", { y: 20, opacity: 0 }, "-=0.3")
  .from(".hero-cta", { scale: 0.8, opacity: 0, ease: "back.out(2)", stagger: 0.15 }, "-=0.2")
  .from(".hero-screenshot", {
    scale: 0.85, rotateX: -15, opacity: 0, ease: "power3.out",
  }, "-=0.4")
  .to(".hero-screenshot", {
    rotateX: 8, scale: 1.08, y: -40, ease: "none",
  });
```

### 3. WorkflowSteps — Pinned, Sequential

**Current:** Static 6-card grid.

**New:** Section pins, cards animate in sequence.

**Pin:** Section pins for ~150vh.

**Animation:**

1. Section heading text reveal (words staggered)
2. 6 cards staggered entrance: `y: 60, opacity: 0, scale: 0.95` → `y: 0, opacity: 1, scale: 1`
3. Each card icon rotate-in: `rotation: -90, scale: 0` → `rotation: 0, scale: 1`
4. Scroll progress: cards highlight sequentially (border color change from `hairline` → `primary`)

**Implementation:**

```tsx
const stepsTl = gsap.timeline({
  scrollTrigger: {
    trigger: stepsRef.current,
    start: "top top",
    end: "+=150%",
    pin: true,
    scrub: 0.3,
  },
});

stepsTl
  .from(".steps-heading .word", { y: 30, opacity: 0, stagger: 0.06 })
  .from(".step-card", {
    y: 60, opacity: 0, scale: 0.95,
    stagger: 0.12, ease: "power2.out",
  })
  .from(".step-icon", {
    rotation: -90, scale: 0,
    stagger: 0.1, ease: "back.out(2)",
  }, "-=0.8");
```

### 4. PainPoints — Scroll-triggered, Counter

**Current:** Static stats cards.

**New:** Scroll-triggered reveals with counter animations.

**Animation:**

1. Heading text reveal
2. Stats numbers: counter animation `0 → value` using `gsap.to` with `snap: { textContent: 1 }` and `textContent` tween
3. Trust chain: each step reveals with stagger, arrows animate between steps
4. Background gradient subtle horizontal shift theo scroll

**Counter implementation:**

```tsx
// For "30-72%" — animate the first number
gsap.from(".stat-value", {
  textContent: 0,
  duration: 2,
  snap: { textContent: 1 },
  ease: "power1.inOut",
  scrollTrigger: { trigger: ".stats-section", start: "top 80%" },
});
```

**Trust chain:** Each pill reveals with `x: -20, opacity: 0` → `x: 0, opacity: 1`, arrows scale in after each pill.

### 5. Features — Scroll-triggered, Parallax Images

**Current:** Static feature cards with hover effect.

**New:** Scroll-triggered with image parallax inside cards.

**Animation:**

1. Heading text reveal
2. 3 feature cards: staggered entrance `y: 50, opacity: 0`
3. Images parallax: `translateY` theo scroll trong mỗi card (±20px range)
4. Tags staggered fade-in within each card
5. 5 secondary feature cards: staggered grid entrance `y: 30, opacity: 0`

**Image parallax:**

```tsx
gsap.to(".feature-img", {
  y: -20,
  ease: "none",
  scrollTrigger: {
    trigger: ".feature-card",
    start: "top bottom",
    end: "bottom top",
    scrub: true,
  },
});
```

### 6. CtaBand — Pinned, Gradient Pulse

**Current:** Static CTA with gradient background.

**New:** Pinned section with animated gradient and text reveal.

**Pin:** Section pins for ~100vh.

**Animation:**

1. Background gradient pulse (scale oscillate, opacity oscillate)
2. Heading text reveal with scale: `scale: 0.9, opacity: 0` → `scale: 1, opacity: 1`
3. CTA buttons magnetic effect
4. 3-4 floating circles: `yoyo: true, repeat: -1` with random y movement

### 7. Footer — Subtle Reveal

**Current:** Static.

**New:** Columns staggered fade-in from bottom.

```tsx
gsap.from(".footer-col", {
  y: 30, opacity: 0,
  stagger: 0.1,
  scrollTrigger: { trigger: "footer", start: "top 90%" },
});
```

## Custom Components

### CustomCursor

**File:** `frontend/components/landing/CustomCursor.tsx`

**Behavior:**
- Outer ring (40px): follows mouse with `quickTo()` — smooth, no lag
- Inner dot (8px): follows faster (less smoothing)
- Hover link/button: ring expands to 80px, opacity drops to 0.5
- `pointer-events: none` on cursor element
- `cursor: none` on body (desktop only)
- Hidden on mobile (< 768px) via `gsap.matchMedia()`

```tsx
export function CustomCursor() {
  const outerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    const outer = outerRef.current!;
    const inner = innerRef.current!;

    const xTo = gsap.quickTo(outer, "x", { duration: 0.4, ease: "power3" });
    const yTo = gsap.quickTo(outer, "y", { duration: 0.4, ease: "power3" });
    const xInner = gsap.quickTo(inner, "x", { duration: 0.15, ease: "power2" });
    const yInner = gsap.quickTo(inner, "y", { duration: 0.15, ease: "power2" });

    const onMouseMove = (e: MouseEvent) => {
      xTo(e.clientX);
      yTo(e.clientY);
      xInner(e.clientX);
      yInner(e.clientY);
    };

    // Hover expand
    const onEnterInteractive = () => {
      gsap.to(outer, { scale: 2, opacity: 0.5, duration: 0.3 });
    };
    const onLeaveInteractive = () => {
      gsap.to(outer, { scale: 1, opacity: 1, duration: 0.3 });
    };

    window.addEventListener("mousemove", onMouseMove);
    // ... attach hover listeners to interactive elements
  });

  return (
    <>
      <div ref={outerRef} className="cursor-outer" />
      <div ref={innerRef} className="cursor-inner" />
    </>
  );
}
```

### TextReveal

**File:** `frontend/components/landing/TextReveal.tsx`

**Purpose:** Split text into words/spans, animate with GSAP.

```tsx
interface TextRevealProps {
  children: string;
  as?: "h1" | "h2" | "h3" | "p";
  className?: string;
  stagger?: number;
  y?: number;
  ease?: string;
}

export function TextReveal({
  children, as: Tag = "h2", className, stagger = 0.06, y = 30, ease = "back.out(1.7)",
}: TextRevealProps) {
  const ref = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    const words = ref.current?.querySelectorAll(".word");
    if (!words?.length) return;

    gsap.from(words, {
      y, opacity: 0, rotationX: -10,
      stagger, ease,
      scrollTrigger: { trigger: ref.current, start: "top 85%" },
    });
  }, { scope: ref });

  const words = children.split(" ").map((w, i) => (
    <span key={i} className="word inline-block" style={{ perspective: 400 }}>
      {w}&nbsp;
    </span>
  ));

  return <Tag ref={ref} className={className}>{words}</Tag>;
}
```

### MagneticButton

**File:** `frontend/components/landing/MagneticButton.tsx`

**Purpose:** Button that follows cursor when hover within ~30px radius.

```tsx
export function MagneticButton({ children, className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  const ref = useRef<HTMLButtonElement>(null);

  const { contextSafe } = useGSAP({ scope: ref });

  const onMouseMove = contextSafe((e: React.MouseEvent) => {
    const btn = ref.current!;
    const rect = btn.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    gsap.to(btn, { x: x * 0.3, y: y * 0.3, duration: 0.3, ease: "power2.out" });
  });

  const onMouseLeave = contextSafe(() => {
    gsap.to(ref.current, { x: 0, y: 0, duration: 0.5, ease: "elastic.out(1, 0.5)" });
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

## CSS Changes

### globals.css additions

```css
/* Custom cursor */
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

/* Hide default cursor on desktop */
@media (min-width: 768px) {
  body { cursor: none; }
  a, button { cursor: none; }
}

/* Navbar scroll state */
.nav-scrolled {
  background: rgba(249, 247, 243, 0.9) !important;
  border-bottom: 1px solid var(--hairline) !important;
}

/* Word inline-block for text reveal */
.word {
  display: inline-block;
  will-change: transform, opacity;
}

/* Step card highlight */
.step-card-active {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 1px var(--primary);
}
```

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `frontend/package.json` | Modify | Add `gsap`, `@gsap/react` |
| `frontend/components/landing/CustomCursor.tsx` | Create | Custom cursor component |
| `frontend/components/landing/TextReveal.tsx` | Create | Reusable text reveal component |
| `frontend/components/landing/MagneticButton.tsx` | Create | Magnetic hover button |
| `frontend/components/landing/Hero.tsx` | Rewrite | GSAP pinned hero with text reveal |
| `frontend/components/landing/WorkflowSteps.tsx` | Rewrite | GSAP pinned steps with stagger |
| `frontend/components/landing/PainPoints.tsx` | Rewrite | GSAP scroll-triggered counters |
| `frontend/components/landing/Features.tsx` | Rewrite | GSAP scroll-triggered with parallax |
| `frontend/components/landing/CtaBand.tsx` | Rewrite | GSAP pinned CTA |
| `frontend/components/landing/Navbar.tsx` | Modify | Add scroll-aware GSAP |
| `frontend/components/landing/Footer.tsx` | Modify | Add subtle GSAP reveal |
| `frontend/app/page.tsx` | Modify | Register GSAP plugins, add CustomCursor |
| `frontend/app/globals.css` | Modify | Add cursor styles, nav-scrolled, word styles |

## Responsive Behavior

Use `gsap.matchMedia()` for breakpoints:

```tsx
gsap.matchMedia().add(
  {
    isDesktop: "(min-width: 768px)",
    isMobile: "(max-width: 767px)",
  },
  (context) => {
    const { isDesktop } = context.conditions;
    // Desktop: full pinned animations
    // Mobile: simplified scroll-triggered (no pin, simpler reveals)
  }
);
```

**Mobile (< 768px):**
- No custom cursor
- No pinned sections (too janky on mobile)
- Simplified scroll-triggered reveals only
- No magnetic buttons
- Text reveal still works but simpler (no rotationX)

**Desktop (>= 768px):**
- Full experience as described above

## Performance Considerations

- Use `will-change: transform, opacity` on animated elements
- `quickTo()` for cursor (interpolated, not raw mouse position)
- `scrub: 0.5` (not `scrub: true`) for smoother scroll-linked animations
- Batch DOM reads/writes — GSAP handles this internally
- Lazy-load GSAP plugins (dynamic import in `useEffect`)
- Avoid animating layout properties (width, height, top, left) — use transforms only

## Non-Goals

- Smooth scroll library (Lenis) — not needed, native scroll is fine
- Page transitions (Barba.js) — single page, no navigation transitions
- 3D/WebGL (Three.js) — overkill for landing page
- Lottie animations — GSAP handles everything needed
