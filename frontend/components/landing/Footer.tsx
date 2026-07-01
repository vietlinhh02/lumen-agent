"use client";

const footerLinks = {
  Product: [
    { label: "Workflow", href: "#workflow" },
    { label: "Features", href: "#features" },
    { label: "Why Lumen", href: "#pain-points" },
  ],
  Research: [
    { label: "Documentation", href: "#" },
    { label: "API Design", href: "#" },
    { label: "Architecture", href: "#" },
  ],
  Team: [
    { label: "About", href: "#" },
    { label: "GitHub", href: "#" },
    { label: "Contact", href: "#" },
  ],
};

export function Footer() {
  return (
    <footer className="bg-surface-deep py-16 lg:py-20">
      <div className="mx-auto max-w-7xl px-6">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-4 lg:gap-12">
          <div className="footer-col col-span-2 md:col-span-4 lg:col-span-1">
            <span className="font-display text-xl font-bold text-on-dark" style={{ letterSpacing: "-0.5px" }}>Lumen</span>
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-on-dark-mute">AI-powered literature review assistant. From search to citation-safe export, in one workspace.</p>
          </div>
          {Object.entries(footerLinks).map(([title, links]) => (
            <div key={title} className="footer-col">
              <h4 className="mb-4 text-sm font-semibold text-on-dark">{title}</h4>
              <ul className="flex flex-col gap-2.5">
                {links.map((link) => (
                  <li key={link.label}>
                    <a href={link.href} className="text-sm text-on-dark-mute transition-colors hover:text-on-dark">{link.label}</a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-12 border-t border-[rgba(255,255,255,0.1)] pt-8">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
            <p className="text-xs text-center text-on-dark-mute sm:text-left">&copy; 2026 Lumen. Built at VinUniversity.</p>
          </div>
        </div>
      </div>
    </footer>
  );
}
