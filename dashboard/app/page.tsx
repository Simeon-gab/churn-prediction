import LandingNav from "@/components/landing/LandingNav";
import Hero from "@/components/landing/Hero";
import ScrollSection from "@/components/landing/ScrollSection";
import {
  ScoringPreview,
  SHAPPreview,
  HubSpotPreview,
} from "@/components/landing/UIPreview";
import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="relative bg-bg min-h-screen">
      <LandingNav />

      {/* ── Hero ──────────────────────────────────────────────────────── */}
      <Hero />

      {/* ── Scroll sections ───────────────────────────────────────────── */}
      <div id="how-it-works" className="border-t border-border/40">
        {/* Section 1: Nightly scoring */}
        <ScrollSection
          id="scoring"
          headline="Nightly scoring, automatic."
          body="Every subscription is scored each night by a Random Forest trained on tenure, usage frequency, support load, and feature adoption. By morning, CSMs have a fresh ranked list — no manual export, no dashboard refresh required."
          ui={<ScoringPreview />}
        />

        {/* Section 2: SHAP explanation — reversed layout */}
        <ScrollSection
          id="explained"
          headline="Explained, not just scored."
          body="A risk score without a reason is just a number. Churn AI uses SHAP to trace each score back to the exact features that drove it — grouped by direction, labeled by impact strength, written for a human to act on."
          ui={<SHAPPreview />}
          reversed
        />

        {/* Section 3: HubSpot sync */}
        <ScrollSection
          id="crm"
          headline="Works inside your CRM."
          body="Risk levels and SHAP explanations sync to HubSpot Company records every morning. CSMs never leave the tool they already work in — they just see a new 'Churn Predictions' section with everything they need to start a retention conversation."
          ui={<HubSpotPreview />}
        />
      </div>

      {/* ── CTA footer ────────────────────────────────────────────────── */}
      <section className="border-t border-border/40 py-24 text-center">
        <div className="max-w-xl mx-auto px-6">
          <h2 className="text-2xl md:text-3xl font-semibold text-text-primary leading-snug tracking-tight">
            Your CS team is flying blind.
            <br />
            <span className="text-text-secondary">Fix that today.</span>
          </h2>
          <p className="mt-4 text-text-secondary">
            502 accounts scored. HubSpot synced. SHAP explanations ready.
          </p>
          <Link
            href="/dashboard"
            className="mt-8 inline-flex px-6 py-3 bg-accent text-bg text-sm font-semibold rounded-md hover:bg-accent/90 transition-colors duration-150"
          >
            Open Dashboard →
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border/40 py-6 text-center">
        <p className="text-xs text-text-tertiary font-mono">
          Churn AI v1.0 · Step 6 of 7 · Built by Gabriel
        </p>
      </footer>
    </div>
  );
}
