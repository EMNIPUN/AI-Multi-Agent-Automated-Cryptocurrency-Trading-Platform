import { LandingHero } from "@/components/landing/LandingHero";
import { LandingNav } from "@/components/landing/LandingNav";
import {
  FAQ,
  FeatureShowcase,
  FinalCTA,
  HowItWorks,
  LandingFooter,
  LogoCloud,
  Pricing,
  StatsBand,
  Testimonials,
} from "@/components/landing/LandingSections";

export function LandingPage() {
  return (
    <div className="relative min-h-screen bg-black text-white">
      <LandingNav />
      <LandingHero />
      <LogoCloud />
      <div aria-hidden className="relative h-24 horizon-glow md:h-36" />
      <FeatureShowcase />
      <StatsBand />
      <HowItWorks />
      <Testimonials />
      <Pricing />
      <FAQ />
      <FinalCTA />
      <LandingFooter />
    </div>
  );
}
