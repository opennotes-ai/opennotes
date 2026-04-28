# Mintlify Integration: `@opennotes/tokens`

> **Audience:** docs maintainers working in `opennotes-docs/`.
>
> **Status:** Implemented by TASK-1460.01. The wiring described in §6 is live:
> `package.json > scripts.vendor:tokens` copies `packages/tokens/src/*.css` into
> `styles/tokens/` (gitignored) before every build, and root-level `style.css`
> `@import`s the vendored files.
>
> **Source of truth for tokens:** [`packages/tokens/`](../packages/tokens/)
> inside the `opennotes` submodule (package name: `@opennotes/tokens`).
>
> **Path references below** are relative to `opennotes-docs/` unless otherwise
> noted. The canonical copy of this spec lives at
> `opennotes/docs/integrations/mintlify-tokens.md`; this copy ships inside the
> docs project for local discoverability.

This document specifies how the Mintlify-based `docs.opennotes.ai` site will
consume the shared `@opennotes/tokens` design system. It locks in a concrete
handoff mechanism so that when TASK-1460.01 scaffolds `opennotes-docs/`, the
docs CI can adopt the tokens without reinventing the integration story.

When `opennotes-docs/` lands, TASK-1460.01 should copy (or link) this file to
`opennotes-docs/INTEGRATION.md` so the docs project carries its integration
spec alongside its code.

## 1. Context

`@opennotes/tokens` is a pnpm-workspace package that ships CSS-only design
tokens (theme variables, fonts, animations). The playground
(`opennotes-playground/`) and platform (`opennotes-platform/`) consume it as a
workspace dep via `@import "@opennotes/tokens";` in their Tailwind v4 entry
CSS.

Mintlify is different. Its build pipeline runs **outside** the pnpm workspace:

- Mintlify Cloud (hosted preview + production) clones the docs repo/path,
  runs `mint build`, and deploys. It does not have visibility into
  `opennotes/packages/tokens/` as an `npm` module unless the package is
  published (or vendored).
- `mint build` consumes `docs.json` plus MDX content. Custom CSS is **not**
  referenced from `docs.json` — the current CLI auto-discovers any `.css`
  file placed at the docs project root (e.g. `style.css`) and injects it
  into every page. See [Mintlify custom scripts docs][mintlify-css].
- The docs project lives (per TASK-1460) at `opennotes/opennotes-docs/` — a
  sibling of `packages/tokens/` inside the `opennotes` submodule.

[mintlify-css]: https://www.mintlify.com/docs/customize/custom-scripts

**Implication:** shipping the same token CSS into Mintlify is either an npm
publish, a build-time file copy, or a wait-until-published block. One of those
three has to be chosen before TASK-1460.01 can apply theme colors consistently
with the rest of the surfaces.

## 2. Three mechanisms considered

### (a) Publish `@opennotes/tokens` to npm / GitHub Packages

Ship the package as a versioned release (e.g., `@opennotes/tokens@0.1.0`),
let `opennotes-docs/package.json` declare it as a regular `dependencies` entry,
and let Mintlify CI `pnpm install` resolve it like any other dep.

**Pros**

- Clean versioning. Docs can pin `0.1.0` and upgrade intentionally.
- Same mechanism works for future external SDK consumers.
- No path-coupling between `opennotes-docs/` and `packages/tokens/`.

**Cons**

- Requires a full npm publish setup (provenance, changeset, npm auth in CI,
  scope ownership, release cadence). None of this exists today for
  `@opennotes/tokens`.
- Tokens are marked `"private": true` in `package.json` today — intentionally,
  because they are iterating. Premature publish locks the API surface.
- Version bump + publish + docs rebuild is a 3-step dance for every token
  tweak during the shared-design-system landing phase (TASK-1468).
- Adds a release gate before any other consumer (including internal ones) can
  pick up a fix.

### (b) Vendor a snapshot of the CSS into `opennotes-docs/` during docs CI

Docs CI copies the CSS files from `packages/tokens/src/` into a vendored
path inside the docs project (e.g., `opennotes-docs/styles/tokens/`) as a
pre-build step. A small root-level `style.css` in `opennotes-docs/` then
`@import`s the vendored files; Mintlify auto-loads `style.css` at build.

**Pros**

- Zero new publishing infrastructure. Three-line `cp` step.
- Always tracks the current `main` of `packages/tokens/` — the whole point
  while tokens are still iterating.
- Mintlify never sees the pnpm workspace; it only sees a plain CSS file at
  the docs project root, which is what its build expects.
- Safe to revert — delete the `styles/tokens/` directory and the CI step.
- Matches the spirit of `"private": true` on the tokens package until an
  external consumer forces publication.

**Cons**

- No independent version pin — docs always get "whatever tokens is at this
  commit."  Mitigated by the fact that `opennotes-docs/` and
  `packages/tokens/` live in the **same submodule** and are bumped together.
- `opennotes-docs/styles/tokens/` is a generated artifact. It must either be
  regenerated in CI every build or committed + kept in sync by a pre-commit
  check. This spec chooses the CI-regen path (no commit) to prevent drift.

### (c) Block Mintlify adoption until `@opennotes/tokens` is npm-published

Ship `opennotes-docs/` with Mintlify defaults for now; revisit theming once
`@opennotes/tokens` has a public release.

**Pros**

- No integration work. Zero risk of drift.

**Cons**

- `docs.opennotes.ai` would visually diverge from `platform.opennotes.ai`
  and the playground during the exact window (m-4) where the shared design
  system is supposed to pay off — poor message for a design-system launch.
- Pushes the integration decision to a future "when we npm-publish"
  checkpoint that is not currently on the roadmap.
- Breaks AC#6 of TASK-1468.03 (a decision must be made, not deferred).

## 3. Chosen mechanism: (b) vendor CSS during docs CI

**Decision:** docs CI copies `packages/tokens/src/*.css` into
`opennotes-docs/styles/tokens/` before `mint build`, and a root `style.css`
in `opennotes-docs/` `@import`s them.

**Rationale**

1. **Matches today's constraints.** `@opennotes/tokens` is `"private": true`
   and will stay that way until an external SDK consumer forces publication.
   Mechanism (a) would require reversing that decision purely to unblock
   docs — weak justification.
2. **Cheap to implement.** Three-line CI step, zero new dependencies, zero new
   release pipelines. See section 6 for the exact step.
3. **Cheap to reverse.** If an external SDK consumer later forces publication,
   swapping (b) → (a) is a five-line `package.json` diff plus a Mintlify
   rebuild. The vendored files and the npm package would ship identical CSS.
4. **Co-located in one submodule.** `opennotes-docs/` and `packages/tokens/`
   both live in `opennotes/`, so bumping the tokens submodule pointer already
   pulls the latest tokens into the next docs build automatically. There is
   no cross-repo sync story.
5. **Tokens are still iterating.** During TASK-1468 we are actively tightening
   the shared token surface. Locking docs to a versioned snapshot now would
   just create churn from version bumps.
6. **No "wait forever" risk.** Unlike (c), (b) lands the integration now.

**Trigger to re-evaluate (switch to (a)):** first external SDK consumer of
`@opennotes/tokens` requesting an npm release, or the moment the tokens
package graduates from `"private": true`. At that point file a follow-up task
to convert the docs CI step from `cp` → `pnpm install` and delete
`styles/tokens/` from the docs project.

## 4. Light / dark variable mapping

Mintlify has a first-class dark mode: it toggles a `dark` class on the root
element when the user picks dark mode. Our tokens follow the same convention
— `packages/tokens/src/theme.css` defines colors under `:root` (light) and
under `.dark` (dark), gated by `@custom-variant dark (&:is(.dark *));`.

**Reality on this site (verified by inspection + TASK-1515.03):** Mintlify
only reads a narrow slice of `@opennotes/tokens`. The rest of the upstream
palette (`--background`, `--foreground`, `--card`, `--popover`, `--muted`,
`--accent`, `--ring`, `--input`, `--border`, `--destructive`, `--chart-*`,
`--radius`) is **inert** here — Mintlify never references those variables.
Importing the full `theme.css` only created a false sense of theming
control; it has been removed.

**The actual Mintlify token contract for this site:**

| Mintlify surface | Where it's set |
|---|---|
| Sidebar active link / focus ring / search highlight (light) | `style.css :root { --primary }` (RGB triplet) |
| Same surfaces (dark) | `style.css .dark { --primary }` |
| Search-highlight / sidebar tinted backgrounds | `--primary-light`, `--primary-dark` (RGB triplets) |
| Internal widgets that don't read CSS vars | `docs.json#colors.primary/light/dark` (hex) |
| Inline body-link accent (light) | `style.css :root { --primary-on-surface }` (RGB triplet) — added by TASK-1515.01 for WCAG AA contrast |
| Syntax highlighting | `--mint-*` vars (Mintlify-owned; not currently overridden) |

The brand teal `oklch(0.65 0.15 165)` is approximated in `docs.json` as
`#3EB489` and as the RGB triplet `0 171 120` in `style.css`. Keep the two in
sync by eye (Mintlify does not interpolate OKLCH into hex).

**Gotcha — OKLCH:** tokens are authored in OKLCH. Mintlify's `docs.json`
colors are hex. Do not try to mirror OKLCH into `docs.json > colors.*` by
eye — keep the documented hex equivalents above.

## 5. Font strategy

`@opennotes/tokens` ships two font entry points, both opt-in:

- `fonts-cdn.css` — imports IBM Plex Sans + Serif from Google Fonts CDN.
- `fonts-self-hosted.css` — imports from `@fontsource/ibm-plex-sans` +
  `@fontsource/ibm-plex-serif` npm packages.

The default `@opennotes/tokens` entry (`index.css`) does **not** import any
fonts; consumers choose explicitly. See
[`packages/tokens/README.md`](../../packages/tokens/README.md#font-strategy).

**Choice for docs:** **CDN (`fonts-cdn.css`).**

Reasons:

- Mintlify already fetches web fonts over the network by default; serving
  IBM Plex from Google Fonts adds no incremental privacy or perf concern
  beyond what Mintlify already does.
- Self-hosted would require vendoring `node_modules/@fontsource/*` font
  files into `opennotes-docs/public/` as part of the CI step — significantly
  more complex than the three-line CSS copy.
- Docs pages are read-once / cacheable. The first-paint cost of CDN fonts is
  amortized across all navigation inside the site.
- `fonts-self-hosted.css` remains available as an opt-in if a
  privacy/bandwidth/CSP constraint emerges later.

Implementation: the root `style.css` explicitly `@import`s
`./styles/tokens/fonts-cdn.css` (alongside `animations.css`; see §6.3).
`theme.css` is no longer imported — see TASK-1515.03 and §4 for why.

## 6. Concrete next action (mechanism (b) implementation spec)

TASK-1460.01 (Mintlify scaffold) must include the following artifacts.

### 6.1 Directory layout in `opennotes-docs/`

```
opennotes-docs/
  docs.json                 # Mintlify config (theme, colors, navigation, etc.)
  style.css                 # root-level, auto-discovered by Mintlify; @imports vendored tokens
  styles/
    tokens/                 # gitignored — populated by CI
      .gitkeep
  .gitignore                # ignores styles/tokens/*.css
  package.json              # scripts.prebuild = vendor step
```

Mintlify's current CLI auto-loads any `.css` file placed at the docs project
root (`style.css`). There is no `styles` field in `docs.json` — the
pre-`docs.json` `mint.json > styles` pattern is deprecated. See
[Mintlify custom scripts docs][mintlify-css].

Rationale for **not** committing the vendored CSS: drift risk. A
CI-regenerated directory is always in sync with whatever
`packages/tokens/src/` is at the current submodule commit.

### 6.2 Vendor step (local dev or Mintlify-Cloud prebuild)

`opennotes-docs/package.json` ships only the CSS files Mintlify actually
consumes — `animations.css` and `fonts-cdn.css` — into the vendored copy:

```json
{
  "scripts": {
    "vendor:tokens": "mkdir -p styles/tokens && cp ../packages/tokens/src/animations.css ../packages/tokens/src/fonts-cdn.css styles/tokens/",
    "prevalidate": "pnpm run vendor:all",
    "predev": "pnpm run vendor:all",
    "prebroken-links": "pnpm run vendor:all"
  }
}
```

`theme.css`, `index.css`, and `fonts-self-hosted.css` are deliberately not
copied: Mintlify never consumes them on this site (see §4). Pruning the
script keeps `styles/tokens/` honest — every vendored file is a file
Mintlify reads. See TASK-1515.03 for the full rationale.

### 6.3 Root `style.css`

`opennotes-docs/style.css` is committed and imports only the consumed
vendored files. The Mintlify-honored RGB triplets for `--primary*` live
inline in the same file, alongside an a11y-fix override that swaps the
`.prose a` border-bottom-color to a darker on-surface teal for WCAG AA
on white. Sketch (see the live file for full comments):

```css
@import "./styles/tokens/animations.css";
@import "./styles/tokens/fonts-cdn.css";

:root {
  --primary: 0 171 120;        /* brand teal — sidebar/badges/widgets */
  --primary-light: 88 198 155;
  --primary-dark: 0 137 96;
  --primary-on-surface: 0 130 82; /* WCAG AA: ~4.87:1 vs white (TASK-1515.01) */
}
.dark { --primary: 0 187 135; }

/* Override Mintlify's prose-anchor border-bottom-color for AA on white.
   Selector mirrors Mintlify's own; style.css loads after the Mintlify
   bundle so a matching-specificity rule wins. Dark mode keeps `--primary`
   because the underline sits on near-black, not white. */
.prose :where(a):not(:where([class~="not-prose"], [class~="not-prose"] *)) {
  border-bottom-color: rgb(var(--primary-on-surface));
}
.dark .prose :where(a):not(:where([class~="not-prose"], [class~="not-prose"] *)) {
  border-bottom-color: rgb(var(--primary));
}
```

`./styles/tokens/index.css` and `./styles/tokens/theme.css` are not
referenced because Mintlify ignores everything in `theme.css` except the
`--primary*` triplets, which are now declared inline in `style.css` for
clarity. `fonts-self-hosted.css` is also unreferenced (CDN fonts only on
this site — see §5).

### 6.4 Mintlify CI step (GitHub Actions, authoritative production build)

For the dedicated docs preview/deploy workflow (TASK-1460.07):

```yaml
# .github/workflows/docs.yml  (illustrative)
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive   # needed because opennotes-docs/ lives in the opennotes submodule
      - name: Vendor @opennotes/tokens CSS into docs
        working-directory: opennotes/opennotes-docs
        run: |
          mkdir -p styles/tokens
          cp ../packages/tokens/src/*.css styles/tokens/
      - name: Install Mintlify CLI
        run: npm i -g mint
      - name: Build
        working-directory: opennotes/opennotes-docs
        run: mint build
```

If `docs.opennotes.ai` is hosted on Mintlify Cloud (recommended per
TASK-1460.06), Mintlify Cloud honors `scripts.prebuild` in `package.json`, so
the `.github/workflows/docs.yml` version above is only needed for the
link-check CI (TASK-1460.07), not for production deploys.

### 6.5 `docs.json` wiring

`docs.json` does **not** reference CSS files. The root `style.css` is picked
up automatically. Keep `docs.json` focused on theme, colors, and navigation:

```json
{
  "$schema": "https://mintlify.com/docs.json",
  "theme": "mint",
  "name": "Open Notes Docs",
  "colors": {
    "primary": "#3EB489",
    "light":   "#3EB489",
    "dark":    "#3EB489"
  }
}
```

The authoritative `--primary*` triplets live in the root `style.css`
(see §6.3); `colors.*` in `docs.json` is the hex fallback for
Mintlify-internal widgets that don't read CSS vars (see §4).

### 6.6 Mintlify version target

At the time of writing, the integration targets the current Mintlify CLI
(`mint`). If the CLI drops root-level `style.css` auto-discovery or
reintroduces a `styles` field, re-validate sections 6.1–6.5 before merging
the upgrade.

## 7. Version update flow

### While mechanism (b) is in effect

- **Every docs build vendors from the current `packages/tokens/src/`
  commit.** A token change on `main` propagates to docs on the next docs
  build. No manual bump, no release.
- **Submodule pointer moves** in the multiverse repo update both playground
  and docs simultaneously. Docs CI on that pointer sees the new tokens.
- **No version field** to track on the docs side. The `@opennotes/tokens`
  package stays at `0.0.1` + `"private": true` throughout.
- **Breaking change protocol:** if a token removal or rename is being
  considered, grep `opennotes-docs/` for the variable in the same PR that
  removes it (same submodule, same `rg` invocation). Note that most
  upstream tokens are not consumed by docs — only the `--primary*` family
  (and indirectly `colors.*` in `docs.json`) actually ships to
  `docs.opennotes.ai`. See §4 for the complete contract.

### After a hypothetical future switch to mechanism (a)

(Documented now so the migration is a mechanical edit, not a redesign.)

- `@opennotes/tokens` flips to `"private": false`, gets a semver release.
- `opennotes-docs/package.json` declares `"@opennotes/tokens": "^0.1.0"` and
  `@import`s from the package (e.g.
  `@import "@opennotes/tokens/theme.css";`) instead of `./styles/tokens/`.
- Docs CI drops the `vendor:tokens` / `prebuild` scripts; adds `pnpm install`
  and lets Mintlify resolve the package normally.
- Token version bumps become explicit: open a PR that bumps the range in
  `opennotes-docs/package.json` to trigger a docs rebuild.
- A webhook from npm to Mintlify Cloud can optionally auto-trigger a docs
  rebuild on publish.

## 8. Follow-up work

- **None required** for mechanism (b). The CI vendor step is the entirety
  of the integration. Implementation happens inside TASK-1460.01 (Mintlify
  scaffold) using the spec in section 6 — coordinated via TASK-1468.12
  (handoff task).
- **If the trigger in section 3 fires** (first external SDK consumer, or the
  `"private": true` flag is removed), file a follow-up task
  `Publish @opennotes/tokens to npm for Mintlify consumption` with labels
  `frontend,design-system,tooling` and link it here. That task replaces the
  `cp` step with a `pnpm install` resolution.
- **AC#5 on TASK-1468.03 coverage:** npm publishing is not required to ship
  the chosen mechanism, so no work is deferred silently — (b) is
  self-contained.

## 9. Cross-references

- Tokens package: [`packages/tokens/README.md`](../../packages/tokens/README.md)
- Parent task: TASK-1460 — Set up Mintlify docs site
- Gating subtask: TASK-1460.01 — Scaffold `opennotes-docs/`
- Source task: TASK-1468.03 — Document Mintlify integration path
- Handoff task: TASK-1468.12 — Mintlify docs CI vendors `@opennotes/tokens`
- Design system landing: TASK-1468 — Extract playground design system into
  `@opennotes/tokens` + `@opennotes/ui`
