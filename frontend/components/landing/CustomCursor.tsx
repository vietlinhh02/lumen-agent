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
