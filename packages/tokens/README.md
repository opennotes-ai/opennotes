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

Self-hosted consumers must also add `@fontsource/ibm-plex-sans` and
`@fontsource/ibm-plex-serif` to their own `dependencies` — see
[Self-hosted migration recipe](#self-hosted-migration-recipe) below.

## Font strategy

**Decision: CDN by default, self-hosted is an explicit opt-in.**

Three mechanisms were considered:

| Mechanism | Default in `index.css` | Chosen |
|---|---|---|
| **CDN-default** — `@import "./fonts-cdn.css"` pulls IBM Plex from `fonts.googleapis.com` | yes | **yes** |
| Self-hosted-default — `@import "./fonts-self-hosted.css"` pulls `@fontsource/*` | no | no |
| Opt-in-only — `index.css` imports no font stylesheet; every consumer picks explicitly | no | no |

Rationale for CDN-default:

- Zero-migration parity with the pre-`@opennotes/tokens` baseline — every existing
  consumer (playground, platform, Mintlify, marketing, Discourse plugin) already
  pulled Google Fonts via `<link>` tags. Flipping to self-hosted would be a
  behavior change for all of them at once.
- Matches TASK-1468.02's conservative "keep `<link>` tags as canonical" stance.
- Self-hosted remains a one-line opt-in via
  `@opennotes/tokens/fonts-self-hosted.css`, so consumers with CSP, privacy,
  or offline constraints can flip themselves without waiting on this package.

## CSP / privacy note

The default entry point (`@opennotes/tokens` → `@opennotes/tokens/fonts-cdn.css`)
issues requests to **`fonts.googleapis.com`** (stylesheet) and
**`fonts.gstatic.com`** (WOFF2 files) on every page load.

If you lock down Content Security Policy, either:

1. Allow the Google origins in both `style-src` and `font-src`:

   ```text
   style-src  'self' https://fonts.googleapis.com;
   font-src   'self' https://fonts.gstatic.com;
   ```

2. Or opt into self-hosted fonts (see
   [Self-hosted migration recipe](#self-hosted-migration-recipe)) and tighten
   CSP to `'self'` only.

Privacy implications of CDN-default:

- Google receives one request per user per session for the stylesheet and
  per-weight WOFF2 files.
- CDN outages degrade typography to system fallbacks — rare, but possible.

## Install weight

`@fontsource/ibm-plex-sans` and `@fontsource/ibm-plex-serif` ship approximately
**~5.4 MB combined on disk** (all weights + WOFF2 + WOFF + TTF + CSS partials).

These are declared as **`optionalDependencies`** of `@opennotes/tokens` rather
than hard dependencies:

- CDN-default consumers (the majority) pay no install cost — if the optional
  install is skipped for any reason, nothing breaks because `fonts-cdn.css`
  never touches `@fontsource/*`.
- Self-hosted consumers should declare `@fontsource/*` as their own direct
  `dependencies` so their install cannot silently skip the fonts. Relying on
  the optional install alone is brittle: pnpm, npm, and yarn all treat
  `optionalDependencies` as best-effort.

## Self-hosted migration recipe

To flip a single consumer from CDN to self-hosted:

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
