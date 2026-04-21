# Visual parity snapshots (TASK-1468.11)

Playwright `toHaveScreenshot()` baselines that catch unintended drift in the design system after the `@opennotes/tokens` + `@opennotes/ui` migration.

## What's covered

- `/login` and `/register` `<main>` regions at desktop (1280x720) and mobile (375x812).
- Both pages exercise:
  - `@opennotes/tokens` CSS variables (background, foreground, primary, border, muted-foreground, ring)
  - IBM Plex Sans / Serif font loading
  - `@opennotes/ui` primitives: `Button`, `Input`, `OAuthButtons`

The simulation detail page (`/simulations/[id]`) is intentionally **not** snapshotted — it crashes with a pre-existing hydration mismatch on this route (see TASK-1468.16 notes; orthogonal to the migration). Re-include it once the hydration issue is resolved.

## Running

```sh
pnpm --filter opennotes-playground exec playwright test tests/visual-parity.spec.ts
```

A failing test produces a diff image alongside the actual/expected pair under `test-results/`. Open it to see the pixel delta.

## Updating baselines

When a token / primitive change is intentional, re-capture:

```sh
pnpm --filter opennotes-playground exec playwright test tests/visual-parity.spec.ts --update-snapshots
```

Inspect the diff in git, commit if it matches the design intent.

## Platform suffix

Playwright tags PNGs with `-chromium-darwin` / `-chromium-linux` etc. The committed baselines are macOS-only; Linux CI runs would generate their own baselines on first capture. CI is not yet wired to run Playwright (only vitest today) — the harness is local-first regression coverage until the playwright job is added.

## Tuning thresholds

`expect.toHaveScreenshot` defaults are configured in `playwright.config.ts`:

- `maxDiffPixelRatio: 0.02` — up to 2% of pixels may differ
- `threshold: 0.2` — per-pixel YIQ tolerance
- `animations: "disabled"`, `caret: "hide"` — for stability

If a true-positive diff is masked by these defaults, tighten them; if false positives appear from font sub-pixel variance across runs, loosen them.
