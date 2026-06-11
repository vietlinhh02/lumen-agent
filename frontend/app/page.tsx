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
import { CustomCursor } from "@/components/landing/CustomCursor";

gsap.registerPlugin(ScrollTrigger);

export default function LandingPage() {
  // Force scroll to top on mount (F5 / page load)
  useEffect(() => {
    window.scrollTo(0, 0);
    // Refresh ScrollTrigger after scroll to top
    setTimeout(() => ScrollTrigger.refresh(), 100);
  }, []);

  return (
    <div className="min-h-screen overflow-x-hidden bg-canvas">
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
