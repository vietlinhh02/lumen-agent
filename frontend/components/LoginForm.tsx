"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";

export default function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Login failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="w-full max-w-[400px]">
      <div className="mb-12 text-center lg:text-left animate-fade-in">
        <Link
          href="/"
          className="font-display text-[20px] font-bold text-ink lg:hidden"
          style={{ letterSpacing: "-0.3px" }}
        >
          Lumen
        </Link>
        <h1
          className="font-display mt-2 text-[40px] font-bold leading-[1.0] text-ink lg:mt-0 animate-slide-up"
          style={{ letterSpacing: "-1px" }}
        >
          Sign in
        </h1>
        <p className="mt-2 text-base leading-[1.5] text-charcoal animate-slide-up delay-100">
          Welcome back. Enter your credentials to continue.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5 animate-slide-up delay-200">
        <div>
          <label
            htmlFor="email"
            className="font-ui mb-1.5 block text-sm font-semibold text-ink"
            style={{ letterSpacing: "-0.3px" }}
          >
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            placeholder="you@example.com"
            className="focus-ring h-[48px] w-full rounded-full bg-surface-card px-5 text-base text-ink placeholder:text-ash outline-none transition-shadow"
            style={{ border: "1px solid var(--hairline)" }}
          />
        </div>

        <div>
          <label
            htmlFor="password"
            className="font-ui mb-1.5 block text-sm font-semibold text-ink"
            style={{ letterSpacing: "-0.3px" }}
          >
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            placeholder="••••••••"
            className="focus-ring h-[48px] w-full rounded-full bg-surface-card px-5 text-base text-ink placeholder:text-ash outline-none transition-shadow"
            style={{ border: "1px solid var(--hairline)" }}
          />
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="font-ui h-[48px] w-full rounded-full bg-primary text-base font-semibold leading-[1.0] text-on-primary transition-colors hover:bg-primary-deep active:bg-primary-deep disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? "Signing in…" : "Sign In"}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-charcoal animate-fade-in delay-300">
        Don&apos;t have an account?{" "}
        <Link href="/login/register" className="font-semibold text-primary hover:text-primary-deep underline underline-offset-2">
          Create one
        </Link>
      </p>
    </div>
  );
}
