"use client";

import { useRef, useEffect } from "react";
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

  useEffect(() => {
    if (!footerRef.current) return;

    const ctx = gsap.context(() => {
      const cols = footerRef.current!.querySelectorAll(".footer-col");

      // SET hidden
      if (cols.length) gsap.set(cols, { y: 30, opacity: 0 });

      // TO visible
      if (cols.length) {
        gsap.to(cols, {
          y: 0, opacity: 1, stagger: 0.1, ease: "power2.out", duration: 0.6,
          scrollTrigger: { trigger: footerRef.current, start: "top 90%", toggleActions: "play none none none" },
        });
      }
    }, footerRef);

    return () => ctx.revert();
  }, []);

  return (
    <footer ref={footerRef} className="bg-surface-deep py-16 lg:py-20">
      <div className="mx-auto max-w-7xl px-6">
        <div className="grid gap-12 lg:grid-cols-4">
          <div className="footer-col">
            <span className="font-display text-xl font-bold text-on-dark" style={{ letterSpacing: "-0.5px" }}>Lumen</span>
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-on-dark-mute">AI-powered literature review assistant. From search to citation-safe export, in one workspace.</p>
          </div>
          {Object.entries(footerLinks).map(([title, links]) => (
            <div key={title} className="footer-col">
              <h4 className="mb-4 text-sm font-semibold text-on-dark">{title}</h4>
              <ul className="flex flex-col gap-2.5">
                {links.map((link) => (
                  <li key={link.label}>
                    <a href={link.href} className="text-sm text-on-dark-mute transition-colors hover:text-on-dark">{link.label}</a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-12 border-t border-[rgba(255,255,255,0.1)] pt-8">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
            <p className="text-xs text-on-dark-mute">&copy; 2026 Lumen. Built at VinUniversity.</p>
            <div className="flex items-center gap-4">
              <span className="rounded-full bg-[rgba(255,255,255,0.08)] px-3 py-1 text-xs text-on-dark-mute">FastAPI + Next.js 16</span>
              <span className="rounded-full bg-[rgba(255,255,255,0.08)] px-3 py-1 text-xs text-on-dark-mute">PostgreSQL + pgvector</span>
              <span className="rounded-full bg-[rgba(255,255,255,0.08)] px-3 py-1 text-xs text-on-dark-mute">LangGraph</span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
