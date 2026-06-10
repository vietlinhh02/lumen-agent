const stats = [
  {
    value: "30-72%",
    label: "of AI-generated citations are fabricated",
    source: "Athaluri et al., 2024",
  },
  {
    value: "1,000+",
    label: "person-hours for a full systematic review",
    source: "Systematic Review Guide, 2026",
  },
  {
    value: "5+",
    label: "disconnected tools cobbled together",
    source: "ResearchGold, 2026",
  },
  {
    value: "288 years",
    label: "to read 105k papers from one search",
    source: "LessWrong",
  },
];

export function PainPoints() {
  return (
    <section id="pain-points" className="bg-surface-dark py-24 lg:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <div className="mb-16 max-w-2xl">
          <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-primary">
            The problem
          </p>
          <h2
            className="font-display text-4xl font-bold leading-[1.0] text-on-dark sm:text-5xl"
            style={{ letterSpacing: "-1px" }}
          >
            Literature reviews are
            <br />
            broken. Here&rsquo;s why.
          </h2>
        </div>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {stats.map((stat, i) => (
            <div
              key={i}
              className="rounded-xl border border-[rgba(255,255,255,0.1)] p-6"
            >
              <p
                className="font-display text-4xl font-bold text-primary"
                style={{ letterSpacing: "-1px" }}
              >
                {stat.value}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-on-dark">
                {stat.label}
              </p>
              <p className="mt-3 text-xs text-on-dark-mute">{stat.source}</p>
            </div>
          ))}
        </div>

        {/* Trust chain */}
        <div className="mt-16 rounded-xl border border-[rgba(255,255,255,0.1)] p-8">
          <p className="mb-6 text-sm font-semibold uppercase tracking-wider text-primary">
            The trust chain
          </p>
          <div className="flex flex-wrap items-center gap-3 text-sm text-on-dark lg:gap-4">
            {[
              "Can't find papers",
              "Don't trust sources",
              "Can't organize",
              "Can't synthesize",
              "AI invents citations",
              "Can't verify",
              "Don't trust output",
            ].map((step, i, arr) => (
              <span key={i} className="flex items-center gap-3">
                <span className="rounded-full bg-[rgba(255,255,255,0.08)] px-3 py-1.5">
                  {step}
                </span>
                {i < arr.length - 1 && (
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    className="hidden text-ash sm:block"
                  >
                    <path d="M5 12h14" />
                    <path d="m12 5 7 7-7 7" />
                  </svg>
                )}
              </span>
            ))}
          </div>
          <p className="mt-6 max-w-2xl text-sm leading-relaxed text-on-dark-mute">
            Lumen breaks this chain by enforcing evidence at every step. Real
            papers from real sources. Structured matrix from saved papers.
            Gaps backed by evidence. Citations validated against your project
            database before export.
          </p>
        </div>
      </div>
    </section>
  );
}
