"use client";

import { useMemo } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

type Part =
  | { type: "text"; value: string }
  | { type: "math"; value: string; display: boolean };

/**
 * Parse a string for inline ($...$) and block ($$...$$) LaTeX delimiters.
 * Returns an ordered list of text/math parts.
 */
function parseLatex(input: string): Part[] {
  const parts: Part[] = [];
  // Match $$...$$ first (greedy by non-$ chars), then $...$ (no newline)
  const regex = /\$\$([^$]+)\$\$|\$([^$\n]+)\$/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(input)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: "text", value: input.slice(lastIndex, match.index) });
    }
    if (match[1] !== undefined) {
      parts.push({ type: "math", value: match[1], display: true });
    } else if (match[2] !== undefined) {
      parts.push({ type: "math", value: match[2], display: false });
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < input.length) {
    parts.push({ type: "text", value: input.slice(lastIndex) });
  }
  return parts;
}

/**
 * Renders a string that may contain inline LaTeX ($...$) or block LaTeX ($$...$$).
 * Unicode math characters (φ, μ, ν, ∇, ℒ, etc.) are rendered as-is in the text portions.
 *
 * Uses KaTeX for math. `throwOnError: false` makes it gracefully degrade to raw
 * text if an expression can't be parsed.
 */
export function MathText({ text, className }: { text: string; className?: string }) {
  const parts = useMemo(() => parseLatex(text ?? ""), [text]);

  return (
    <span className={className}>
      {parts.map((part, i) => {
        if (part.type === "text") {
          return <span key={i}>{part.value}</span>;
        }
        try {
          const html = katex.renderToString(part.value, {
            throwOnError: false,
            displayMode: part.display,
            output: "html",
            strict: false,
            trust: false,
          });
          return (
            <span
              key={i}
              // KaTeX's renderToString with trust:false produces sanitized HTML
              // and only renders the math expression we passed in (not user HTML).
              dangerouslySetInnerHTML={{ __html: html }}
            />
          );
        } catch {
          return <span key={i}>{part.value}</span>;
        }
      })}
    </span>
  );
}
