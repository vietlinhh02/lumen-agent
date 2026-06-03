import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-canvas px-6">
      <div className="max-w-md text-center">
        <p
          className="font-display text-[180px] font-bold leading-[1.0] animate-fade-in"
          style={{
            letterSpacing: "-4px",
            background: "linear-gradient(135deg, #ea2804, #ff6a3d, #f4a8a0)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          404
        </p>

        <h1
          className="mt-6 font-display text-[32px] font-bold leading-[1.2] text-ink animate-slide-up delay-100"
          style={{ letterSpacing: "-0.5px" }}
        >
          Page not found
        </h1>

        <p className="mt-3 text-base leading-[1.5] text-body animate-slide-up delay-200">
          The page you are looking for does not exist or has been moved.
        </p>

        <Link
          href="/"
          className="mt-8 inline-flex h-11 items-center rounded-full bg-surface-dark px-6 text-[16px] font-semibold leading-none text-on-dark transition-colors hover:bg-ink animate-slide-up delay-300"
        >
          Back to Home
        </Link>
      </div>
    </div>
  );
}
