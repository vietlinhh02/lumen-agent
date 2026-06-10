const features = [
  {
    title: "Multi-Source Search",
    description:
      "Search across Semantic Scholar, OpenAlex, arXiv, Exa, and Firecrawl in one query. Partial results shown when one source fails.",
    image: "https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=600&q=80&auto=format",
    imageAlt: "Library with rows of bookshelves",
    tags: ["5 sources", "Language audit", "Deduplication"],
  },
  {
    title: "Literature Matrix",
    description:
      "AI extracts method, dataset, key result, limitation, and relevance for each paper. Edit any cell — your corrections persist.",
    image: "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=600&q=80&auto=format",
    imageAlt: "Notes and data spread across a desk",
    tags: ["Structured data", "Editable", "Confidence scores"],
  },
  {
    title: "Citation Guardrail",
    description:
      "The backend validates every citation ID against your saved project papers. Invalid references are rejected before export. No hallucinated bibliography.",
    image: "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=600&q=80&auto=format",
    imageAlt: "Open books stacked on a desk",
    tags: ["Backend validation", "DB-backed", "Export-ready"],
  },
];

export function Features() {
  return (
    <section id="features" className="py-24 lg:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <div className="mb-16 max-w-2xl">
          <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-primary">
            Core capabilities
          </p>
          <h2
            className="font-display text-4xl font-bold leading-[1.0] tracking-tight text-ink sm:text-5xl"
            style={{ letterSpacing: "-1px" }}
          >
            Everything you need.
            <br />
            Nothing you don&rsquo;t.
          </h2>
          <p className="mt-4 text-lg text-body">
            Eight features, zero fluff. Every capability supports the evidence
            chain from search to export.
          </p>
        </div>

        <div className="grid gap-8 lg:grid-cols-3">
          {features.map((feature, i) => (
            <div
              key={i}
              className="group overflow-hidden rounded-xl border border-hairline bg-surface-card transition-all hover:border-hairline-strong hover:shadow-lg"
            >
              <div className="relative h-48 overflow-hidden">
                <img
                  src={feature.image}
                  alt={feature.imageAlt}
                  className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-surface-dark/40 to-transparent" />
              </div>
              <div className="p-6">
                <h3 className="mb-2 text-lg font-semibold text-ink">
                  {feature.title}
                </h3>
                <p className="mb-4 text-sm leading-relaxed text-charcoal">
                  {feature.description}
                </p>
                <div className="flex flex-wrap gap-2">
                  {feature.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full border border-hairline bg-canvas px-3 py-1 text-xs font-medium text-charcoal"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Secondary features grid */}
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {[
            {
              title: "Knowledge Map",
              desc: "Interactive graph of papers, methods, datasets.",
            },
            {
              title: "Research Gaps",
              desc: "Evidence-backed gap detection with paper references.",
            },
            {
              title: "Conflict Detection",
              desc: "Flag opposing findings across studies.",
            },
            {
              title: "PDF Ingestion",
              desc: "Download, extract, and chunk full-text PDFs.",
            },
            {
              title: "Agent Audit",
              desc: "Full LangGraph workflow transparency.",
            },
          ].map((item, i) => (
            <div
              key={i}
              className="rounded-xl border border-hairline bg-surface-card p-4"
            >
              <h4 className="mb-1 text-sm font-semibold text-ink">
                {item.title}
              </h4>
              <p className="text-xs leading-relaxed text-charcoal">
                {item.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
