"use client";

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
