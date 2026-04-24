import Link from "next/link";

export default function LandingNav() {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/50 bg-bg/80 backdrop-blur-sm">
      <div className="max-w-6xl mx-auto px-6 md:px-10 h-14 flex items-center justify-between">
        <span className="text-accent font-semibold text-sm tracking-wide">
          Churn AI
        </span>

        <nav className="flex items-center gap-6">
          <a
            href="#how-it-works"
            className="text-sm text-text-secondary hover:text-text-primary transition-colors duration-150"
          >
            How it works
          </a>
          <Link
            href="/dashboard"
            className="text-sm font-medium px-3 py-1.5 rounded border border-border hover:border-text-tertiary text-text-primary transition-colors duration-150"
          >
            Open Dashboard
          </Link>
        </nav>
      </div>
    </header>
  );
}
