"use client";

import { useRef, useEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

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

  useEffect(() => {
    if (!sectionRef.current) return;

    const ctx = gsap.context(() => {
      const heading = sectionRef.current!.querySelector(".steps-heading");
      const cards = sectionRef.current!.querySelectorAll(".step-card");
      const icons = sectionRef.current!.querySelectorAll(".step-icon");

      // Split heading text
      if (heading) {
        const h2 = heading.querySelector("h2");
        if (h2) {
          const text = h2.textContent || "";
          h2.innerHTML = text
            .split(" ")
            .map(
              (w) =>
                `<span class="word">${w}&nbsp;</span>`
            )
            .join("");
        }
      }

      const words = heading?.querySelectorAll(".word") || [];

      // 1. SET hidden state immediately (before any scroll)
      if (words.length) gsap.set(words, { y: 30, opacity: 0 });
      if (cards.length) gsap.set(cards, { y: 60, opacity: 0, scale: 0.95 });
      if (icons.length) gsap.set(icons, { rotation: -90, scale: 0 });

      // 2. TO visible when scroll trigger fires
      if (words.length) {
        gsap.to(words, {
          y: 0,
          opacity: 1,
          stagger: 0.06,
          ease: "back.out(1.7)",
          duration: 0.8,
          scrollTrigger: {
            trigger: sectionRef.current,
            start: "top 75%",
            toggleActions: "play none none none",
          },
        });
      }

      if (cards.length) {
        gsap.to(cards, {
          y: 0,
          opacity: 1,
          scale: 1,
          stagger: 0.1,
          ease: "power2.out",
          duration: 0.6,
          scrollTrigger: {
            trigger: sectionRef.current,
            start: "top 70%",
            toggleActions: "play none none none",
          },
        });
      }

      if (icons.length) {
        gsap.to(icons, {
          rotation: 0,
          scale: 1,
          stagger: 0.08,
          ease: "back.out(2)",
          duration: 0.5,
          scrollTrigger: {
            trigger: sectionRef.current,
            start: "top 65%",
            toggleActions: "play none none none",
          },
        });
      }
    }, sectionRef);

    ScrollTrigger.refresh();
    return () => ctx.revert();
  }, []);

  return (
    <section
      ref={sectionRef}
      id="workflow"
      className="bg-surface-bone pb-24 pt-36 lg:pb-32 lg:pt-48"
    >
      <div className="mx-auto max-w-7xl px-6">
        <div className="steps-heading mb-16 max-w-2xl">
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
