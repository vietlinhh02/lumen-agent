"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";

export default function RegisterForm() {
  const { register, login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    if (password !== confirmPassword) {
      toast.error("Passwords do not match.");
      return;
    }

    if (password.length < 8) {
      toast.error("Password must be at least 8 characters.");
      return;
    }

    setIsSubmitting(true);
    try {
      await register(email, password);
      toast.success("Account created. Signing you in…");
      await login(email, password);
      router.push("/");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="w-full max-w-[400px]">
      <div className="mb-12 text-center lg:text-left animate-fade-in">
        <span
          className="font-display text-[20px] font-bold text-ink lg:hidden"
          style={{ letterSpacing: "-0.3px" }}
        >
          Lumen
        </span>
        <h1
          className="font-display mt-2 text-[40px] font-bold leading-[1.0] text-ink lg:mt-0 animate-slide-up"
          style={{ letterSpacing: "-1px" }}
        >
          Create account
        </h1>
        <p className="mt-2 text-base leading-[1.5] text-charcoal animate-slide-up delay-100">
          Start your AI-powered literature review journey.
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
            autoComplete="new-password"
            placeholder="At least 8 characters"
            className="focus-ring h-[48px] w-full rounded-full bg-surface-card px-5 text-base text-ink placeholder:text-ash outline-none transition-shadow"
            style={{ border: "1px solid var(--hairline)" }}
          />
        </div>

        <div>
          <label
            htmlFor="confirmPassword"
            className="font-ui mb-1.5 block text-sm font-semibold text-ink"
            style={{ letterSpacing: "-0.3px" }}
          >
            Confirm password
          </label>
          <input
            id="confirmPassword"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            autoComplete="new-password"
            placeholder="Repeat your password"
            className="focus-ring h-[48px] w-full rounded-full bg-surface-card px-5 text-base text-ink placeholder:text-ash outline-none transition-shadow"
            style={{ border: "1px solid var(--hairline)" }}
          />
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="font-ui h-[48px] w-full rounded-full bg-primary text-base font-semibold leading-[1.0] text-on-primary transition-colors hover:bg-primary-deep active:bg-primary-deep disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-charcoal animate-fade-in delay-300">
        Already have an account?{" "}
        <Link href="/login" className="font-semibold text-primary hover:text-primary-deep underline underline-offset-2">
          Sign in
        </Link>
      </p>
    </div>
  );
}
