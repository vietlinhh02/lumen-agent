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
