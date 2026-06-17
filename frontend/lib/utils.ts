import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const NAIVE_API_DATETIME_RE =
  /^\d{4}-\d{2}-\d{2}(?:T|\s)\d{2}:\d{2}:\d{2}(?:\.\d+)?$/;

export function parseApiDate(value: string): Date {
  const normalized = NAIVE_API_DATETIME_RE.test(value)
    ? `${value.replace(" ", "T")}Z`
    : value;
  return new Date(normalized);
}

export function formatDate(iso: string) {
  return parseApiDate(iso).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

export function formatAuthors(authors: Array<{ name: string; author_id?: string }>) {
  if (!authors || authors.length === 0) return "Unknown authors";
  const names = authors.map((a) => a.name);
  if (names.length <= 3) return names.join(", ");
  return `${names.slice(0, 3).join(", ")} et al.`;
}

export function relativeTime(iso: string): string {
  const diff = Date.now() - parseApiDate(iso).getTime();
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return formatDate(iso);
}

export function paperLabel(count: number): string {
  if (count === 0) return "No papers";
  if (count === 1) return "1 paper";
  return `${count} papers`;
}
