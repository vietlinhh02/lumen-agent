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

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    setLoggedIn(!!token && !isTokenExpired(token));
  }, []);

  useGSAP(() => {
    if (!sectionRef.current) return;

    const heading = sectionRef.current.querySelector(".cta-heading");

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

    // Gradient pulse — infinite
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

    // Floating circles — infinite
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

    // Heading reveal with scale — scroll-triggered (not pinned)
    if (heading) {
      gsap.from(heading.querySelectorAll(".word"), {
        scale: 0.9,
        opacity: 0,
        stagger: 0.08,
        ease: "back.out(1.7)",
        duration: 0.8,
        scrollTrigger: {
          trigger: heading,
          start: "top 85%",
          toggleActions: "play none none none",
        },
      });
    }

    // CTA buttons
    const ctaButtons = sectionRef.current.querySelector(".cta-buttons");
    if (ctaButtons) {
      gsap.from(
        ctaButtons.children,
        {
          scale: 0.8,
          opacity: 0,
          ease: "back.out(2)",
          stagger: 0.15,
          duration: 0.6,
          scrollTrigger: {
            trigger: ctaButtons,
            start: "top 85%",
            toggleActions: "play none none none",
          },
        }
      );
    }

    // Subtitle
    const subtitle = sectionRef.current.querySelector(".cta-subtitle");
    if (subtitle) {
      gsap.from(subtitle, {
        y: 20,
        opacity: 0,
        duration: 0.6,
        ease: "power2.out",
        scrollTrigger: {
          trigger: subtitle,
          start: "top 85%",
          toggleActions: "play none none none",
        },
      });
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
        <div className="cta-heading">
          <h2
            className="font-display text-4xl font-bold leading-[1.0] text-on-dark sm:text-5xl lg:text-6xl"
            style={{ letterSpacing: "-1.5px" }}
          >
            Ready to illuminate your research?
          </h2>
        </div>
        <p className="cta-subtitle mx-auto mt-6 max-w-md text-lg text-on-dark-mute">
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
