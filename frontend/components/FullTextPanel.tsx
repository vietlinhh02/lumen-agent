"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import { X } from "@phosphor-icons/react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { FullTextResponse, FullTextChunk } from "@/lib/types";

interface GroupedSection {
  label: string;
  path: string;
  chunks: FullTextChunk[];
  totalChars: number;
}

function groupChunks(chunks: FullTextChunk[]): GroupedSection[] {
  const groups = new Map<string, GroupedSection>();

  for (const chunk of chunks) {
    const key = chunk.section_label || "Full Text";
    if (!groups.has(key)) {
      groups.set(key, {
        label: key,
        path: chunk.section_path || key,
        chunks: [],
        totalChars: 0,
      });
    }
    const group = groups.get(key)!;
    group.chunks.push(chunk);
    group.totalChars += chunk.char_count;
  }

  return Array.from(groups.values());
}

interface MarkdownSection {
  heading: string;
  level: number;
  body: string;
}

function parseMarkdownSections(md: string): MarkdownSection[] {
  const lines = md.split("\n");
  const sections: MarkdownSection[] = [];
  let current: MarkdownSection | null = null;

  for (const line of lines) {
    const match = line.match(/^(#{1,4})\s+(.+)/);
    if (match) {
      if (current) sections.push(current);
      current = {
        heading: match[2].trim(),
        level: match[1].length,
        body: "",
      };
    } else if (current) {
      current.body += line + "\n";
    } else {
      if (!current) {
        current = { heading: "", level: 0, body: "" };
      }
      current.body += line + "\n";
    }
  }
  if (current) sections.push(current);

  const cleaned = sections.map((s) => ({
    ...s,
    body: s.body.replace(/\n+$/, "").trim(),
  }));

  // Filter out empty sections (e.g. "## Methodology" with no body before next heading)
  return cleaned.filter((s) => s.body.length > 0 || s.level === 0);
}

function normalizeExtractedText(text: string): string {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

function chunksToMarkdown(chunks: FullTextChunk[]): string {
  return groupChunks(chunks)
    .map((group) => {
      const body = group.chunks
        .map((chunk) => normalizeExtractedText(chunk.chunk_text))
        .filter(Boolean)
        .join("\n\n");
      return `## ${group.label}\n\n${body}`;
    })
    .join("\n\n");
}

export function FullTextPanel({
  data,
  onClose,
}: {
  data: FullTextResponse;
  onClose: () => void;
}) {
  const [expandedSection, setExpandedSection] = useState<string | null>(null);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const isRaw = data.full_text_status === "raw_extracted";
  const hasMarkdown = !!data.crawled_markdown?.trim();
  const displayMarkdown = useMemo(() => {
    if (hasMarkdown) return data.crawled_markdown!.trim();
    if (data.full_text_status === "completed" && data.chunks.length > 0) {
      return chunksToMarkdown(data.chunks);
    }
    return "";
  }, [data.chunks, data.crawled_markdown, data.full_text_status, hasMarkdown]);
  const hasDisplayMarkdown = displayMarkdown.length > 0;
  const hasLlmMarkdown = hasMarkdown;

  const markdownSections = useMemo(() => {
    if (!hasDisplayMarkdown) return [];
    return parseMarkdownSections(displayMarkdown);
  }, [displayMarkdown, hasDisplayMarkdown]);

  const groupedChunks = useMemo(
    () => (isRaw || hasDisplayMarkdown ? [] : groupChunks(data.chunks)),
    [data.chunks, isRaw, hasDisplayMarkdown]
  );

  // The new pdf-oxide path produces chunks without an LLM normalize pass.
  // Legacy paths may produce a crawled_markdown (LLM-normalized) or just
  // raw chunks waiting in `raw_extracted`. The badge + subtitle reflect
  // which one the user is looking at.
  const showAsLlmNormalized = data.full_text_status === "completed" && hasLlmMarkdown;
  const showAsIndexed = data.full_text_status === "completed" && !hasLlmMarkdown && data.chunks.length > 0;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm animate-fade-in"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div
        className="w-full max-w-[900px] max-h-[85vh] rounded-[16px] bg-surface-card shadow-xl animate-scale-in flex flex-col overflow-hidden"
        style={{ border: "1px solid var(--hairline)" }}
      >
        <div className="flex items-start justify-between gap-4 border-b px-6 py-4 shrink-0" style={{ borderColor: "var(--hairline)" }}>
          <div className="min-w-0 flex-1">
            <h2 className="font-display text-[18px] font-bold leading-[1.3] text-ink truncate" style={{ letterSpacing: "-0.3px" }}>
              {data.title}
            </h2>
            <p className="mt-0.5 text-[12px] text-ash">
              {isRaw
                ? "Raw text — LLM normalization pending"
                : showAsLlmNormalized
                  ? `${markdownSections.length} sections · LLM-normalized`
                  : showAsIndexed
                    ? `${groupedChunks.length} sections · ${data.total_chunks} chunks · pdf-oxide`
                    : hasDisplayMarkdown
                      ? `${markdownSections.length} sections`
                      : `${groupedChunks.length} sections · ${data.total_chunks} chunks`}
              {" · "}{data.total_chars.toLocaleString()} chars
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className={`font-ui rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
              isRaw ? "bg-amber-50 text-amber-700" :
              showAsLlmNormalized ? "bg-emerald-50 text-emerald-700" :
              showAsIndexed ? "bg-sky-50 text-sky-700" :
              "bg-ash/10 text-ash"
            }`}>
              {isRaw ? "Raw" :
               showAsLlmNormalized ? "Normalized" :
               showAsIndexed ? "Indexed" :
               data.full_text_status || "Unknown"}
            </span>
            <button
              onClick={onClose}
              className="flex h-[32px] w-[32px] items-center justify-center rounded-full text-charcoal hover:bg-surface-bone hover:text-ink transition-colors"
            >
              <X size={16} weight="bold" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto raw-text-scroll">
          {data.chunks.length === 0 && !hasDisplayMarkdown ? (
            <div className="px-6 py-4">
              <p className="text-sm text-ash">No text available.</p>
            </div>
          ) : isRaw ? (
            <div className="space-y-4 py-4">
              {data.chunks.map((chunk, i) => {
                const lineCount = chunk.chunk_text.split("\n").length;
                return (
                  <div key={i} className="space-y-3">
                    <div className="flex items-center gap-3 px-6 text-[12px] text-ash">
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-0.5 font-semibold text-amber-700">
                        Raw
                      </span>
                      <span>{lineCount} lines</span>
                      <span>{chunk.char_count.toLocaleString()} chars</span>
                      <span className="ml-auto text-[11px] text-ash/60">
                        LLM normalization will clean this into sections
                      </span>
                    </div>
                    <div
                      className="bg-amber-50/30 py-4 font-mono text-[13px] leading-[1.8] text-ink whitespace-pre-wrap break-words text-center raw-text-scroll"
                      style={{ borderTop: "1px solid rgba(251,191,36,0.2)", borderBottom: "1px solid rgba(251,191,36,0.2)", maxHeight: "60vh", overflowY: "auto", paddingLeft: "24px", paddingRight: "24px" }}
                    >
                      {chunk.chunk_text}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : hasDisplayMarkdown ? (
            <div className="px-6 py-4 space-y-1">
              {markdownSections.map((section, i) => {
                const isOpen = expandedSection === `m${i}`;
                return (
                  <div
                    key={i}
                    className="rounded-[10px] border overflow-hidden transition-all"
                    style={{ borderColor: "var(--hairline)" }}
                  >
                    <button
                      onClick={() => setExpandedSection(isOpen ? null : `m${i}`)}
                      className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left hover:bg-surface-bone transition-colors"
                    >
                      <div className="min-w-0 flex-1 flex items-center gap-2">
                        {section.level > 0 && (
                          <span className="font-mono text-[10px] text-ash bg-surface-bone rounded px-1 py-0.5 shrink-0">
                            H{section.level}
                          </span>
                        )}
                        <span className={`font-ui font-semibold text-ink truncate ${
                          section.level <= 1 ? "text-[14px]" : section.level === 2 ? "text-[13px]" : "text-[12px]"
                        }`}>
                          {section.heading || "Introduction"}
                        </span>
                      </div>
                      <span className="font-ui shrink-0 text-[11px] text-ash">
                        {section.body.length.toLocaleString()} chars
                      </span>
                    </button>
                    {isOpen && (
                      <div className="border-t px-5 py-4" style={{ borderColor: "var(--hairline)" }}>
                        <div className="markdown-body max-h-[500px] overflow-y-auto">
                          <Markdown remarkPlugins={[remarkGfm]}>{section.body}</Markdown>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="px-6 py-4 space-y-2">
              {groupedChunks.map((group, i) => {
                const isOpen = expandedSection === `s${i}`;
                return (
                  <div
                    key={i}
                    className="rounded-[10px] border overflow-hidden transition-all"
                    style={{ borderColor: "var(--hairline)" }}
                  >
                    <button
                      onClick={() => setExpandedSection(isOpen ? null : `s${i}`)}
                      className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left hover:bg-surface-bone transition-colors"
                    >
                      <div className="min-w-0 flex-1">
                        <span className="font-ui text-[13px] font-semibold text-ink block truncate">
                          {group.label}
                        </span>
                        {group.path !== group.label && (
                          <span className="font-ui text-[11px] text-ash block truncate mt-0.5">
                            {group.path}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {group.chunks.length > 1 && (
                          <span className="font-ui text-[10px] text-ash bg-surface-bone rounded-full px-1.5 py-0.5">
                            {group.chunks.length} chunks
                          </span>
                        )}
                        <span className="font-ui text-[11px] text-ash">
                          {group.totalChars.toLocaleString()} chars
                        </span>
                      </div>
                    </button>
                    {isOpen && (
                      <div className="border-t px-4 py-3 space-y-3" style={{ borderColor: "var(--hairline)" }}>
                        {group.chunks.map((chunk, j) => (
                          <div key={j}>
                            {group.chunks.length > 1 && (
                              <p className="text-[10px] text-ash mb-1 font-mono">
                                Chunk {j + 1} · {chunk.content_type} · {chunk.char_count.toLocaleString()} chars
                              </p>
                            )}
                            <pre className="font-ui whitespace-pre-wrap break-words text-[12px] leading-[1.7] text-ink max-h-[400px] overflow-y-auto">
                              {chunk.chunk_text}
                            </pre>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
