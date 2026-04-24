"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

interface Props {
  headline: string;
  body: string;
  ui: React.ReactNode;
  reversed?: boolean;
  id?: string;
}

export default function ScrollSection({
  headline,
  body,
  ui,
  reversed = false,
  id,
}: Props) {
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    gsap.registerPlugin(ScrollTrigger);
    const el = sectionRef.current;
    if (!el) return;

    // Fade up the entire section as it enters the viewport — once, no replay
    gsap.from(el, {
      opacity: 0,
      y: 40,
      duration: 0.7,
      ease: "power2.out",
      scrollTrigger: {
        trigger: el,
        start: "top 82%",
        once: true,
      },
    });

    return () => {
      ScrollTrigger.getAll().forEach((t) => t.kill());
    };
  }, []);

  return (
    <section
      ref={sectionRef}
      id={id}
      className={`max-w-6xl mx-auto px-6 md:px-10 py-24 flex flex-col md:flex-row items-center gap-12 md:gap-20 ${
        reversed ? "md:flex-row-reverse" : ""
      }`}
    >
      {/* Text column */}
      <div className="flex-1 max-w-md">
        <h2 className="text-2xl md:text-3xl font-semibold text-text-primary leading-snug tracking-tight">
          {headline}
        </h2>
        <p className="mt-4 text-text-secondary leading-relaxed">{body}</p>
      </div>

      {/* UI mockup column */}
      <div className="flex-1 w-full max-w-md">{ui}</div>
    </section>
  );
}
