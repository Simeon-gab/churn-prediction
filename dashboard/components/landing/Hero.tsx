"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import Link from "next/link";

export default function Hero() {
  const badgeRef   = useRef<HTMLSpanElement>(null);
  const titleRef   = useRef<HTMLHeadingElement>(null);
  const subRef     = useRef<HTMLParagraphElement>(null);
  const ctaRef     = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // GSAP lives only on the landing page. power2.out = decelerate entrance.
    const tl = gsap.timeline({ defaults: { ease: "power2.out" } });

    tl.from(badgeRef.current, { opacity: 0, y: 12, duration: 0.4 })
      .from(titleRef.current, { opacity: 0, y: 24, duration: 0.6 }, "-=0.1")
      .from(subRef.current,   { opacity: 0, y: 16, duration: 0.5 }, "-=0.3")
      .from(ctaRef.current,   { opacity: 0, y: 12, duration: 0.4 }, "-=0.2");
  }, []);

  return (
    <section className="min-h-screen flex flex-col justify-center pt-14">
      {/* Subtle radial glow behind the headline */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 overflow-hidden"
      >
        <div
          className="absolute -top-40 left-1/2 -translate-x-1/2 w-[900px] h-[600px] rounded-full opacity-[0.06]"
          style={{ background: "radial-gradient(circle, #00D87E 0%, transparent 70%)" }}
        />
      </div>

      <div className="relative max-w-6xl mx-auto px-6 md:px-10 py-24">
        {/* Badge */}
        <span
          ref={badgeRef}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-border bg-surface text-xs text-text-secondary font-mono mb-8"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-accent inline-block" />
          v1.0 · Nightly scoring + HubSpot sync
        </span>

        {/* Headline */}
        <h1
          ref={titleRef}
          className="text-4xl sm:text-5xl md:text-6xl font-semibold text-text-primary leading-[1.1] tracking-tight max-w-3xl"
        >
          Know which accounts<br />
          are about to churn.
          <br />
          <span className="text-text-secondary">Before they do.</span>
        </h1>

        {/* Subtext */}
        <p
          ref={subRef}
          className="mt-6 text-lg text-text-secondary leading-relaxed max-w-xl"
        >
          Churn AI scores every subscription nightly, explains the risk in plain
          English with SHAP, and pushes alerts into the CRM your team already
          lives in — no spreadsheets, no guessing.
        </p>

        {/* CTA */}
        <div ref={ctaRef} className="mt-8 flex items-center gap-4">
          <Link
            href="/dashboard"
            className="px-5 py-2.5 bg-accent text-bg text-sm font-semibold rounded-md hover:bg-accent/90 transition-colors duration-150"
          >
            Open Dashboard
          </Link>
          <a
            href="#how-it-works"
            className="text-sm text-text-secondary hover:text-text-primary transition-colors duration-150"
          >
            How it works →
          </a>
        </div>
      </div>
    </section>
  );
}
