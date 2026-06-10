# Reports Page — Mobile Responsive Design

## Problem

The current reports page (`frontend/app/(app)/reports/page.tsx`) uses a desktop-only
split-view layout: a fixed 240px left panel for the report list and a right panel for
the detail preview. On mobile screens (< 768px), the left panel consumes most of the
viewport, leaving almost no room for the detail content. The header with the project
dropdown also overflows on narrow screens. The page is unusable on phones.

## Goal

Make the reports page fully responsive across three breakpoints:

- **Mobile (< 768px):** Stack & Push pattern — list full-width, tap to push detail full-screen.
- **Tablet (768px–1023px):** Narrow split view with reduced padding.
- **Desktop (≥ 1024px):** Current layout unchanged.

## Decision

| Area | Choice | Rationale |
|------|--------|-----------|
| Approach | Single file + Tailwind responsive classes | Consistent with existing codebase, minimal file churn |
| Mobile navigation | Stack & Push | User chose this; matches iOS Mail pattern |
| Breakpoints | `sm` (640px), `md` (768px), `lg` (1024px), `xl` (1280px) | Standard Tailwind, matches AppShell |
| TOC sidebar on mobile | Hidden, use existing TocDropdown | Already implemented |
| Content padding | `px-4 sm:px-6 lg:px-10` | Progressive reduction |
| New button on mobile | Inline in header (not FAB) | Simpler, no overlay complexity |

## Breakpoint Behavior

### Mobile (< 768px)

**List state (`selectedId === null`):**
- Header: "Literature Reviews" title wraps, project dropdown takes full width below
- Report list: full-width cards with status badge, title, citation count
- "New" button: inline in header row
- Left panel: full width (`w-full`)

**Detail state (`selectedId !== null`):**
- Left panel: hidden (`hidden`)
- Right panel: full width, takes entire viewport
- Header: back arrow + validation badge + search (compact) + sections dropdown + export button
- Content: `px-4` padding, section cards `rounded-[8px]`
- TOC sidebar: hidden (use TocDropdown)
- Section headings: `text-[18px]` (down from 20px)
- Paragraph text: `text-[14px]` (down from 15px)

**Back navigation:**
- Back button in toolbar sets `selectedId(null)` → returns to list
- No animation, CSS show/hide only

### Tablet (768px–1023px)

- Left panel: `w-[200px]` (reduced from 240px)
- Detail content: `px-6` padding
- TOC sidebar: hidden, use TocDropdown
- Header: single row, project dropdown `max-w-[200px]`

### Desktop (≥ 1024px)

- No changes from current layout
- Left panel: `w-[240px]`
- Detail content: `px-10`
- TOC sidebar: visible on `lg:` when toc.length > 2

## Specific Changes

### 1. Outer Container

```
Before: className="fixed inset-0 top-[60px] ... ml-0 xl:ml-[56px]"
After:  className="fixed inset-0 top-[60px] ... ml-0 xl:ml-[56px]"
```

No change needed — already handles sidebar offset.

### 2. Header Bar

```
Before: className="px-6 pt-3 pb-2.5 flex items-center gap-4"
After:  className="px-4 sm:px-6 pt-3 pb-2.5 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4"
```

- Title + divider + dropdown: wrap on mobile, single row on sm+
- Divider: hidden on mobile (`hidden sm:block`)

### 3. Split View Container

```
Before: className="flex-1 flex min-h-0"
After:  className="flex-1 flex min-h-0"
```

No change — the panels themselves handle responsive visibility.

### 4. Left Panel (Report List)

```
Before: className="w-[240px] shrink-0 ..."
After:  className="w-full md:w-[200px] lg:w-[240px] shrink-0 ..."
```

- Mobile: full width, hidden when detail is selected
- Tablet: 200px
- Desktop: 240px

Add visibility toggle:
```
className={`... ${selectedId ? "hidden md:flex" : "flex"}`}
```

### 5. Right Panel (Detail)

```
Before: className="flex-1 bg-canvas flex flex-col min-w-0"
After:  className="flex-1 bg-canvas flex flex-col min-w-0"
```

Add visibility toggle on mobile:
```
className={`... ${selectedId ? "flex" : "hidden md:flex"}`}
```

### 6. Detail Toolbar

- Back button: visible on mobile when `selectedId` is set (already exists)
- Search input: `max-w-[140px] sm:max-w-xs` on mobile
- "Export" button: icon-only on mobile, icon+text on sm+
- Validation badge: always visible

### 7. Content Area

```
Before: className="px-10 py-8 space-y-6"
After:  className="px-4 sm:px-6 lg:px-10 py-5 sm:py-8 space-y-4 sm:space-y-6"
```

### 8. Section Cards

```
Before: className="rounded-[12px] ..."
After:  className="rounded-[8px] sm:rounded-[12px] ..."
```

Heading padding:
```
Before: className="px-8 pt-6 pb-3"
After:  className="px-4 sm:px-6 lg:px-8 pt-4 sm:pt-6 pb-2 sm:pb-3"
```

Content padding:
```
Before: className="... px-8 ..."
After:  className="... px-4 sm:px-6 lg:px-8 ..."
```

### 9. Typography

- Section headings: `text-[18px] sm:text-[20px]`
- Paragraph text: `text-[14px] sm:text-[15px]`
- Reference items: no change (already small)

### 10. References Section

- Grid layout: already single-column, no change needed
- Reference card padding: `px-3 py-2` (keep)

### 11. Audit Pills

```
Before: className="flex items-center gap-5 flex-wrap"
After:  className="flex items-center gap-3 sm:gap-5 flex-wrap"
```

### 12. Generate Button (bottom of list)

- Full width on mobile: `w-full`
- Standard width on sm+: keep as is

## Files to Modify

| File | Change |
|------|--------|
| `frontend/app/(app)/reports/page.tsx` | All responsive changes |

No new files. No new dependencies.

## What Stays Unchanged

- All data fetching logic
- All state management
- All API calls
- Desktop layout (≥ 1024px)
- TocDropdown component
- AuditPill component
- Markdown rendering
- Job polling logic
- Export logic

## Testing

- Verify on iPhone SE (375px) — list and detail both usable
- Verify on iPad (768px) — narrow split works
- Verify on desktop (1280px+) — no regression
- Verify back navigation on mobile
- Verify project dropdown wraps properly on mobile
- Verify search input is usable on mobile
- Verify export button is reachable on mobile
