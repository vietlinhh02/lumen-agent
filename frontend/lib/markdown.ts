export interface TocEntry {
  id: string;
  text: string;
  level: number;
}

export interface ParsedSection {
  id: string;
  heading: string;
  level: number;
  content: string;
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

export function extractText(children: React.ReactNode): string {
  if (typeof children === "string") return children;
  if (typeof children === "number") return String(children);
  if (!children) return "";
  if (Array.isArray(children)) return children.map(extractText).join("");
  if (typeof children === "object" && "props" in children) {
    return extractText((children as React.ReactElement<{ children?: React.ReactNode }>).props.children);
  }
  return "";
}

export function normalizeMarkdownForDisplay(markdown: string): string {
  const normalized = markdown.replace(/\r\n?/g, "\n");
  const lines = normalized.split("\n");
  const nonBlankLines = lines.filter((line) => line.trim().length > 0);

  if (nonBlankLines.length === 0) {
    return normalized;
  }

  const commonIndent = Math.min(
    ...nonBlankLines.map((line) => line.match(/^ */)?.[0].length ?? 0),
  );

  if (commonIndent === 0) {
    return normalized;
  }

  return lines.map((line) => line.slice(commonIndent)).join("\n");
}

export function parseSections(markdown: string): ParsedSection[] {
  const lines = normalizeMarkdownForDisplay(markdown).split("\n");
  const sections: ParsedSection[] = [];
  let current: ParsedSection | null = null;
  const idCounts = new Map<string, number>();

  function nextSectionId(heading: string): string {
    const baseId = slugify(heading) || "section";
    const count = (idCounts.get(baseId) ?? 0) + 1;
    idCounts.set(baseId, count);
    return count === 1 ? baseId : `${baseId}-${count}`;
  }

  function pushCurrent() {
    if (!current) return;
    sections.push({
      ...current,
      content: normalizeMarkdownForDisplay(current.content),
    });
  }

  for (const line of lines) {
    const match = line.match(/^(#{1,3})\s+(.+)$/);
    if (match) {
      pushCurrent();
      const heading = match[2].replace(/\*+/g, "").trim();
      current = {
        id: nextSectionId(heading),
        heading,
        level: match[1].length,
        content: "",
      };
    } else if (current) {
      current.content += line + "\n";
    } else {
      current = {
        id: "_intro",
        heading: "",
        level: 1,
        content: line + "\n",
      };
    }
  }
  pushCurrent();
  return sections;
}

export function buildToc(sections: ParsedSection[]): TocEntry[] {
  return sections
    .filter((s) => s.heading)
    .map((s) => ({ id: s.id, text: s.heading, level: s.level }));
}
