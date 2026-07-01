"use client";

import { useEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

import { Navbar } from "@/components/landing/Navbar";
import { Hero } from "@/components/landing/Hero";
import { WorkflowSteps } from "@/components/landing/WorkflowSteps";
import { PainPoints } from "@/components/landing/PainPoints";
import { Features } from "@/components/landing/Features";
import { CtaBand } from "@/components/landing/CtaBand";
import { Footer } from "@/components/landing/Footer";

gsap.registerPlugin(ScrollTrigger);

export default function LandingPage() {
  useEffect(() => {
    // Let the browser handle scroll restoration, or reset it:
    if (typeof window !== "undefined" && window.history) {
      window.history.scrollRestoration = "manual";
    }
    
    // Refresh ScrollTrigger after a slight delay to allow layout to settle
    const t1 = setTimeout(() => ScrollTrigger.refresh(), 100);
    const t2 = setTimeout(() => ScrollTrigger.refresh(), 500); // safety net
    
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, []);

  return (
    <div className="min-h-screen overflow-x-hidden bg-canvas">
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
