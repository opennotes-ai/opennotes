# @opennotes/tokens

Framework-agnostic CSS design tokens for Open Notes surfaces.

Ships theme variables, fonts, and animations as pure CSS — no JS runtime, no
build step, no framework assumptions. Consumed by Solid apps (playground,
platform), documentation sites (Mintlify), the Discourse plugin, and future
marketing surfaces.

## Entry points

| Import | What you get |
|---|---|
| `@opennotes/tokens` | Everything (theme + fonts via CDN + animations) |
| `@opennotes/tokens/theme.css` | Tailwind v4 `@theme inline`, `:root`, `.dark` OKLCH variables |
| `@opennotes/tokens/fonts.css` | IBM Plex Sans + Serif via Google Fonts CDN (default) |
| `@opennotes/tokens/fonts-cdn.css` | Same as `fonts.css` — explicit CDN variant |
| `@opennotes/tokens/fonts-self-hosted.css` | IBM Plex Sans + Serif via `@fontsource/*` |
| `@opennotes/tokens/animations.css` | `content-show`, `content-hide`, `anchor-fade` keyframes + `.anchor-highlight` |

## Usage

### Tailwind v4 app (Solid playground / platform)

```css
/* src/app.css */
@import "tailwindcss";
@import "@opennotes/tokens";
```

### Opt into self-hosted fonts

Skip the CDN (offline builds, CSP constraints, privacy): import the parts
individually.

```css
@import "tailwindcss";
@import "@opennotes/tokens/theme.css";
@import "@opennotes/tokens/fonts-self-hosted.css";
@import "@opennotes/tokens/animations.css";
```

The `@fontsource/ibm-plex-sans` and `@fontsource/ibm-plex-serif` packages are
declared as dependencies of `@opennotes/tokens` so transitive CSS `@import`s
resolve without the consumer adding them directly.

## Design notes

- **Tailwind v4 only.** The `@theme inline` block uses Tailwind v4 syntax.
  Consumers on Tailwind v3 should import `theme.css` surgically or copy
  specific variable blocks.
- **OKLCH colors.** Values are authored in OKLCH; browsers that can't render
  OKLCH fall back per Tailwind's own color fallback strategy.
- **No JS entry.** This package ships CSS only — `type: "module"` is set for
  package-manager hygiene, not for JavaScript imports.
