# Blog Feed Landing Page Wireframe

## Overview

Two-column landing page with a long-scroll blog feed (left, wider) and the existing simulations list (right, narrower). Blog posts render fully inline with markdown prose styling, modeled after Simon Willison's blog — dense, readable, news-feed rather than article index.

## Components

- BlogFeed: Server-rendered list of published posts from Supabase
- BlogPost: Single post with title, date, and prose HTML from markdown
- SimulationsList: Existing simulation cards (extracted from current index.tsx)
- FontToggle: Sans/serif toggle for blog reading preference
- LoadMoreButton: Fetches next page of posts

## Mobile Layout (375px)

```
┌───────────────────────────────────┐
│ [Logo]          [Aa] [◐] [Sign in]│
├───────────────────────────────────┤
│                                   │
│  Blog                             │
│  ───                              │
│                                   │
│  Post Title One                   │
│  March 18, 2026                   │
│                                   │
│  Full prose body rendered from    │
│  markdown. Dense readable text    │
│  flowing naturally. Paragraphs,   │
│  code blocks, links — all inline. │
│  Up to ~800 words per post.       │
│                                   │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │
│                                   │
│  Another Post Title               │
│  March 16, 2026                   │
│                                   │
│  More prose body text flowing     │
│  naturally in the feed. Code      │
│  snippets, links, emphasis all    │
│  rendered inline.                 │
│                                   │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │
│                                   │
│  [ Load more posts ]              │
│                                   │
├───────────────────────────────────┤
│                                   │
│  Simulations                      │
│  ───────────                      │
│  3 simulations found              │
│                                   │
│  ┌─────────────────────────────┐  │
│  │ Sim bafod-dizul  Completed  │  │
│  │ Created: Mar 14, 2026       │  │
│  │ Agents: 10  Notes: 50       │  │
│  └─────────────────────────────┘  │
│                                   │
│  ┌─────────────────────────────┐  │
│  │ Sim gutij-bahop  Running    │  │
│  │ Created: Mar 12, 2026       │  │
│  │ Agents: 8   Notes: 32       │  │
│  └─────────────────────────────┘  │
│                                   │
│  Pagination: [< 1 2 3 >]         │
│                                   │
└───────────────────────────────────┘
```

## Desktop Layout (1024px+)

```
┌──────────────────────────────────────────────────────────────────────┐
│ [Logo]                                          [Aa] [◐] [Sign in]  │
├──────────────────────────────────────────┬───────────────────────────┤
│                                          │                           │
│  Blog                                    │  Simulations              │
│  ───                                     │  ───────────              │
│                                          │  3 simulations found      │
│  Post Title One                          │                           │
│  March 18, 2026                          │  ┌─────────────────────┐  │
│                                          │  │ Sim bafod   Completed│  │
│  Full prose body rendered from markdown. │  │ Mar 14 · 10a · 50n  │  │
│  Dense readable text flowing naturally   │  └─────────────────────┘  │
│  across the wider column. Paragraphs,    │                           │
│  code blocks, inline code, links, bold,  │  ┌─────────────────────┐  │
│  italic — all rendered as HTML from the  │  │ Sim gutij   Running  │  │
│  markdown source. Each post can be up    │  │ Mar 12 · 8a  · 32n  │  │
│  to ~800 words, displayed fully without  │  └─────────────────────┘  │
│  any truncation or "read more" links.    │                           │
│                                          │  ┌─────────────────────┐  │
│  This mirrors the dense, long-scroll     │  │ Sim nolap   Pending  │  │
│  style of simonwillison.net — a feed of  │  │ Mar 10 · 12a · 0n   │  │
│  fully readable posts, not an index.     │  └─────────────────────┘  │
│                                          │                           │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │  [< 1 2 3 >]             │
│                                          │                           │
│  Another Post Title                      │         ▲                 │
│  March 16, 2026                          │   sticky positioned       │
│                                          │   stays in view while     │
│  More prose content here. Could include  │   scrolling blog feed     │
│  code blocks like:                       │         ▼                 │
│                                          │                           │
│  ```python                               │                           │
│  def score(note):                        │                           │
│      return bayesian_average(note)       │                           │
│  ```                                     │                           │
│                                          │                           │
│  And continue with analysis text after   │                           │
│  the code block.                         │                           │
│                                          │                           │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │                           │
│                                          │                           │
│  [ Load more posts ]                     │                           │
│                                          │                           │
└──────────────────────────────────────────┴───────────────────────────┘

Grid: grid-cols-[2fr_1fr], gap-8, max-w-6xl
```

## Interactions

### Font Toggle [Aa]
- Click: toggles blog prose between IBM Plex Sans and IBM Plex Serif
- Persists to localStorage (key: "blog-font-preference")
- Default: sans (matches existing site font)
- Only affects prose content in blog posts, not UI chrome

### Load More Button
- Click: fetches next 10 posts via Supabase offset pagination
- Appends to existing list (no page reload)
- Disappears when no more posts available
- Shows loading state while fetching

### Simulations Column (Desktop)
- Sticky positioned (top-20) — stays visible while scrolling blog feed
- Existing pagination behavior unchanged

### Blog Post Separator
- Dashed border between posts (border-dashed border-border)
- Generous vertical spacing (py-8) between posts

## Data Requirements

### blog_posts table (Supabase)
- `id`: uuid (PK, default gen_random_uuid())
- `title`: text (not null)
- `slug`: text (unique, not null)
- `body_markdown`: text (not null, ~800 words soft max)
- `published_at`: timestamptz (nullable — null = draft)
- `created_at`: timestamptz (default now())
- `updated_at`: timestamptz (default now())

### Query
```sql
SELECT id, title, slug, body_markdown, published_at
FROM blog_posts
WHERE published_at IS NOT NULL
ORDER BY published_at DESC
LIMIT 10 OFFSET :offset
```

### RLS Policy
- anon/authenticated: SELECT where published_at IS NOT NULL
- No INSERT/UPDATE/DELETE from client

## States

### Loading (Blog Feed)
```
│  Blog                              │
│  ───                               │
│  Loading posts...                  │
```

### Empty (No Posts)
```
│  Blog                              │
│  ───                               │
│  No posts yet. Check back soon.    │
```

### Error (Supabase Unreachable)
```
│  Blog                              │
│  ───                               │
│  Failed to load posts.             │
```

## Accessibility Notes

- Semantic HTML: `<article>` for each post, `<time>` for dates
- Blog heading hierarchy: h2 for section, h3 for post titles
- Font toggle: aria-label "Switch to serif/sans font"
- Prose content inherits proper heading levels via markdown
- Code blocks: `<pre><code>` with language class for screen readers
