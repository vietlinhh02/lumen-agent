"use client";

import { useRef, useEffect } from "react";
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

  useEffect(() => {
    if (!sectionRef.current) return;

    const ctx = gsap.context(() => {
      const heading = sectionRef.current!.querySelector(".pp-heading");
      const statCards = sectionRef.current!.querySelectorAll(".stat-card");
      const pills = sectionRef.current!.querySelectorAll(".trust-pill");
      const arrows = sectionRef.current!.querySelectorAll(".trust-arrow");

      // Split heading text
      if (heading) {
        const h2 = heading.querySelector("h2");
        if (h2) {
          const text = h2.textContent || "";
          h2.innerHTML = text
            .split(" ")
            .map(
              (w) =>
                `<span class="word" style="perspective:400px">${w}&nbsp;</span>`
            )
            .join("");
        }
      }

      // Heading text reveal
      const words = heading?.querySelectorAll(".word") || [];
      if (words.length) {
        gsap.from(words, {
          y: 30,
          opacity: 0,
          stagger: 0.06,
          ease: "back.out(1.7)",
          duration: 0.8,
          immediateRender: false,
          scrollTrigger: {
            trigger: heading,
            start: "top 90%",
            toggleActions: "play none none none",
          },
        });
      }

      // Counter animations for stats
      const statValues = sectionRef.current!.querySelectorAll(".stat-value");
      statValues.forEach((el) => {
        const target = parseInt(el.getAttribute("data-target") || "0", 10);
        const counter = { value: 0 };
        gsap.to(counter, {
          value: target,
          duration: 2,
          ease: "power1.inOut",
          immediateRender: false,
          scrollTrigger: {
            trigger: el,
            start: "top 90%",
            toggleActions: "play none none none",
          },
          onUpdate: () => {
            el.textContent = Math.round(counter.value).toString();
          },
        });
      });

      // Stat cards entrance
      if (statCards.length) {
        gsap.from(statCards, {
          y: 40,
          opacity: 0,
          stagger: 0.1,
          ease: "power2.out",
          duration: 0.6,
          immediateRender: false,
          scrollTrigger: {
            trigger: sectionRef.current,
            start: "top 80%",
            toggleActions: "play none none none",
          },
        });
      }

      // Trust chain pills reveal
      if (pills.length) {
        gsap.from(pills, {
          x: -20,
          opacity: 0,
          stagger: 0.08,
          ease: "power2.out",
          duration: 0.5,
          immediateRender: false,
          scrollTrigger: {
            trigger: ".trust-chain",
            start: "top 90%",
            toggleActions: "play none none none",
          },
        });
      }

      if (arrows.length) {
        gsap.from(arrows, {
          scale: 0,
          opacity: 0,
          stagger: 0.08,
          ease: "back.out(2)",
          duration: 0.4,
          immediateRender: false,
          scrollTrigger: {
            trigger: ".trust-chain",
            start: "top 90%",
            toggleActions: "play none none none",
          },
          delay: 0.2,
        });
      }
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <section
      ref={sectionRef}
      id="pain-points"
      className="bg-surface-dark py-24 lg:py-32"
    >
      <div className="mx-auto max-w-7xl px-6">
        <div className="pp-heading mb-16 max-w-2xl">
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
              className="stat-card rounded-xl border border-[rgba(255,255,255,0.1)] p-6"
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
