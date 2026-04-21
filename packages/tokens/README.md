# @opennotes/tokens

Framework-agnostic CSS design tokens for Open Notes surfaces.

Ships theme variables, fonts, and animations as pure CSS — no JS runtime, no
build step, no framework assumptions. Consumed by Solid apps (playground,
platform), documentation sites (Mintlify), the Discourse plugin, and future
marketing surfaces.

## Entry points

| Import | What you get |
|---|---|
| `@opennotes/tokens` | Theme variables + animations (no fonts) |
| `@opennotes/tokens/theme.css` | Tailwind v4 `@theme inline`, `:root`, `.dark` OKLCH variables |
| `@opennotes/tokens/animations.css` | `content-show`, `content-hide`, `anchor-fade` keyframes + `.anchor-highlight` |
| `@opennotes/tokens/fonts-cdn.css` | IBM Plex Sans + Serif via Google Fonts CDN (opt-in) |
| `@opennotes/tokens/fonts-self-hosted.css` | IBM Plex Sans + Serif via `@fontsource/*` (opt-in; requires consumer install) |

`@opennotes/tokens/fonts.css` is kept as an alias of `fonts-cdn.css` for
backward compatibility; new consumers should prefer the explicit
`fonts-cdn.css` / `fonts-self-hosted.css` names.

## Usage

### Tailwind v4 app (Solid playground / platform)

Default (no fonts — use SSR `<link>` tags or add a font entry point
explicitly):

```css
/* src/app.css */
@import "tailwindcss";
@import "@opennotes/tokens";
```

Opt in to CDN fonts via CSS (small apps without SSR `<link>` control):

```css
/* src/app.css */
@import "tailwindcss";
@import "@opennotes/tokens";
@import "@opennotes/tokens/fonts-cdn.css";
```

Opt in to self-hosted fonts (offline builds, CSP constraints, privacy) —
requires `@fontsource/*` in your own `dependencies`:

```css
@import "tailwindcss";
@import "@opennotes/tokens/theme.css";
@import "@opennotes/tokens/fonts-self-hosted.css";
@import "@opennotes/tokens/animations.css";
```

See [Self-hosted migration recipe](#self-hosted-migration-recipe) below.

## Font strategy

**Decision: fonts are opt-in.** The default `@opennotes/tokens` entry ships
theme variables and animations only; consumers choose a font-loading strategy
explicitly (SSR `<link>` tags, CDN `@import`, or self-hosted `@fontsource/*`).

Why opt-in rather than CDN-by-default:

- **CSP / privacy postures differ across consumers.** Platform ships with a
  tight CSP and had zero font requests pre-migration; silently adding
  `fonts.googleapis.com` requests because of a token import would be a
  behavior regression.
- **Not every consumer needs fonts.** Platform pre-migration didn't load
  IBM Plex at all; the Discourse plugin runs inside Discourse's own font
  stack. Forcing a font import would be dead payload for those surfaces.
- **Playground controls FOUC via SSR `<link>` preload.** Duplicating that
  via `@import` produces double requests and complicates the eventual
  removal of the `<link>` tags (see `entry-server.tsx` TODO →
  TASK-1468.11).

Only the playground was loading Google Fonts via `<link>` tags pre-migration;
the earlier "every existing consumer already pulled Google Fonts" framing was
too broad.

**Re-evaluate the opt-in default** if more than 50% of consumers end up
explicitly opting into `fonts-cdn.css`. At that point, flipping the default
back to CDN becomes the lower-friction choice.

## CSP / privacy note

`@opennotes/tokens/fonts-cdn.css` issues requests to
**`fonts.googleapis.com`** (stylesheet) and **`fonts.gstatic.com`** (WOFF2
files) on every page load. Only consumers that explicitly `@import` that
entry point (or ship their own Google Fonts `<link>` tags) are affected.

If you lock down Content Security Policy and want CDN fonts, allow the Google
origins in both `style-src` and `font-src`:

```text
style-src  'self' https://fonts.googleapis.com;
font-src   'self' https://fonts.gstatic.com;
```

If you want tighter CSP (`'self'` only), opt into self-hosted fonts (see
[Self-hosted migration recipe](#self-hosted-migration-recipe)).

## Install weight

`@fontsource/ibm-plex-sans` and `@fontsource/ibm-plex-serif` ship approximately
**~5.4 MB combined on disk** (all weights + WOFF2 + WOFF + TTF + CSS partials).

These are declared as **`peerDependencies`** of `@opennotes/tokens` with
`peerDependenciesMeta.optional = true`, not as direct or optional
dependencies:

- CDN-default consumers (the majority) **do not install** `@fontsource/*` —
  pnpm skips optional peers by default and nothing in `fonts-cdn.css` touches
  them, so nothing breaks.
- Self-hosted consumers **must** add `@fontsource/ibm-plex-sans` and
  `@fontsource/ibm-plex-serif` to their own `dependencies`. This is
  explicit and audit-visible; the previous `optionalDependencies` shape
  quietly installed fontsource into every consumer (pnpm installs optional
  deps by default), defeating the purpose.

## Self-hosted migration recipe

To flip a single consumer from CDN (or no-fonts) to self-hosted:

1. Add `@fontsource/*` as direct dependencies of the consumer:

   ```sh
   pnpm --filter <consumer> add @fontsource/ibm-plex-sans @fontsource/ibm-plex-serif
   ```

2. Replace the `@opennotes/tokens` import with the split form in the
   consumer's root CSS (e.g. `src/app.css`):

   ```css
   /* before */
   @import "@opennotes/tokens";

   /* after */
   @import "@opennotes/tokens/theme.css";
   @import "@opennotes/tokens/fonts-self-hosted.css";
   @import "@opennotes/tokens/animations.css";
   ```

3. Tighten CSP if desired: remove `fonts.googleapis.com` /
   `fonts.gstatic.com` from `style-src` / `font-src`.

No changes to `@opennotes/tokens` itself are required.

## Design notes

- **Tailwind v4 only.** The `@theme inline` block uses Tailwind v4 syntax.
  Consumers on Tailwind v3 should import `theme.css` surgically or copy
  specific variable blocks.
- **OKLCH colors.** Values are authored in OKLCH; browsers that can't render
  OKLCH fall back per Tailwind's own color fallback strategy.
- **No JS entry.** This package ships CSS only — `type: "module"` is set for
  package-manager hygiene, not for JavaScript imports.
