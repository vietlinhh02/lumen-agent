import { Navbar } from "@/components/landing/Navbar";
import { Hero } from "@/components/landing/Hero";
import { WorkflowSteps } from "@/components/landing/WorkflowSteps";
import { PainPoints } from "@/components/landing/PainPoints";
import { Features } from "@/components/landing/Features";
import { CtaBand } from "@/components/landing/CtaBand";
import { Footer } from "@/components/landing/Footer";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-canvas">
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
