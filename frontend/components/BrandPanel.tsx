export default function BrandPanel() {
  return (
    <div className="hidden flex-col justify-between bg-surface-dark p-12 lg:flex lg:w-[45%]">
      <span
        className="font-display text-[24px] font-bold text-on-dark animate-fade-in"
        style={{ letterSpacing: "-0.5px" }}
      >
        Lumen
      </span>

      <div className="max-w-md">
        <h2
          className="font-display text-[56px] font-bold leading-[1.0] text-on-dark animate-slide-in-left delay-200"
          style={{ letterSpacing: "-1.5px" }}
        >
          Illuminate
          <br />
          your research.
        </h2>
        <p className="mt-6 text-lg leading-[1.56] text-on-dark-mute animate-fade-in delay-400">
          AI-powered literature analysis that helps you navigate, summarize,
          and discover insights across thousands of papers.
        </p>
      </div>

      <p className="text-xs text-on-dark-mute animate-fade-in delay-400">
        &copy; 2025 Lumen. All rights reserved.
      </p>
    </div>
  );
}
