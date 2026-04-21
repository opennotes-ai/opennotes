# @opennotes/ui

Shared Solid UI components, utilities, and palettes for Open Notes surfaces.

See [TASK-1468](../../backlog/tasks/) for the design history behind this
package (extracted from `opennotes-playground` so `opennotes-platform` and
future admin surfaces can reuse the primitives).

## Distribution: source-only

`@opennotes/ui` is a **source-only workspace package**. There is no build
step. Consumers must use a Solid-aware bundler (Vite + `vite-plugin-solid`);
the `exports` map points at `./src/*.ts` / `./src/*.tsx` files with JSX
preserved, which is then transformed by `vite-plugin-solid` at consumer
build time. `@solidjs/start` automatically adds the `solid` condition to
Vite's resolve conditions, so `"solid"` entries in the exports map win.

This avoids duplicating the Solid runtime between consumers (single
`solid-js@1.9.x` instance is verified via `pnpm why solid-js`).

## Entry points

```ts
// Primitives (subpath pattern keeps the component graph tree-shakable)
import { Button } from "@opennotes/ui/components/ui/button";
import { Badge, type BadgeVariant } from "@opennotes/ui/components/ui/badge";
import InlineHistogram from "@opennotes/ui/components/ui/inline-histogram";

// Higher-level components (barrel)
import { ModeToggle, OAuthButtonsRow } from "@opennotes/ui/components";

// Generic utilities (cn, softHyphenate, anchor-scroll, proquint/UUID helpers)
import { cn, formatIdBadgeLabel } from "@opennotes/ui/utils";

// Visual palettes for the scoring / rating domain
import { SEMANTIC_COLORS, TIER_DESCRIPTIONS } from "@opennotes/ui/palettes";
```

The root export `@opennotes/ui` re-exports everything for convenience.

## Peer dependencies

Consumers install these themselves so each app keeps a **single** instance
of `solid-js`, `@kobalte/core`, and friends:

- `solid-js@^1.9`
- `@solidjs/router@^0.15`
- `@kobalte/core@^0.13` — headless primitives under `components/ui/*`
- `class-variance-authority@^0.7` — variant class builders (badge, button, toggle)
- `clsx@^2.1` — used by `cn`
- `tailwind-merge@^3` — used by `cn`
- `echarts@^6` — required only when consuming `components/ui/echart`

`@fontsource/*` and `@opennotes/tokens` fonts remain opt-in (see
`@opennotes/tokens`).

Do **not** add `shamefully-hoist=true` to any `.npmrc` — it defeats the
peer-dep check.

## Scoping note — domain-coupled palettes

`@opennotes/ui/palettes` intentionally encodes Community Notes scoring
concepts (rating enums, scorer tiers, simulation action keys). That is the
visual language of the design system, shared across playground / platform /
future admin UIs.

Pure display formatters with CN enum pretty-printing (e.g., `humanizeLabel`,
`LABEL_MAP`) live in `opennotes-playground/src/lib/format.ts` rather than
here. If a second consumer needs them, see `TASK-1468.13` (scoping revisit).

## Commands

```sh
pnpm --filter @opennotes/ui type-check  # tsc --noEmit
pnpm --filter @opennotes/ui test        # vitest
```

There is no `build` or `dev` — source is consumed directly via `vite-plugin-solid`.

## Constraints

- ESM only. No CJS.
- Source under `src/` uses relative imports or bare specifiers — no
  `~/...` aliases — so code compiles unchanged from any sibling package.
- `solid-js`, `@kobalte/core`, `class-variance-authority`, `clsx`,
  `tailwind-merge`, `echarts`, and `@solidjs/router` are `peerDependencies`.
  They are listed under `devDependencies` only for local type-checking.
