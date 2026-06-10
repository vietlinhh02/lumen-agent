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
    return extractText((children as React.ReactElement).props.children);
  }
  return "";
}

export function parseSections(markdown: string): ParsedSection[] {
  const lines = markdown.split("\n");
  const sections: ParsedSection[] = [];
  let current: ParsedSection | null = null;

  for (const line of lines) {
    const match = line.match(/^(#{1,3})\s+(.+)$/);
    if (match) {
      if (current) sections.push(current);
      const heading = match[2].replace(/\*+/g, "").trim();
      current = {
        id: slugify(heading),
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
  if (current) sections.push(current);
  return sections;
}

export function buildToc(sections: ParsedSection[]): TocEntry[] {
  return sections
    .filter((s) => s.heading)
    .map((s) => ({ id: s.id, text: s.heading, level: s.level }));
}
