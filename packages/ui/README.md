# @opennotes/ui

Shared Solid UI components, utilities, and palettes for Open Notes surfaces.

## Status

Scaffold only. This package ships with empty entry points that later subtasks fill in:

- TASK-1468.05 moves shared utilities (`cn`) and component tests out of the playground.
- TASK-1468.06 moves shared Solid components (Badge, Button, Skeleton, etc.) and palettes.
- TASK-1468.07 wires the platform app to consume this package.

## Entry points

Consumers import from subpath exports:

```ts
import { cn } from "@opennotes/ui/utils";
import { Badge } from "@opennotes/ui/components";
import { palette } from "@opennotes/ui/palettes";
```

The root export `@opennotes/ui` re-exports everything for convenience.

## Peer dependencies

`solid-js`, `@kobalte/core`, `class-variance-authority`, `clsx`, and `tailwind-merge` are declared as peer dependencies. Consumers (playground, platform) install them explicitly so a single instance of `solid-js` exists per app (verified with `pnpm why solid-js`). Do not add `shamefully-hoist=true` to any `.npmrc` in the workspace.

## Build

The package builds with [`tsup`](https://tsup.egoist.dev/) in ESM-only mode. Each entry point emits `.js` plus `.d.ts` into `dist/`. Source maps and declaration maps are enabled.

```sh
pnpm --filter @opennotes/ui build       # one-shot
pnpm --filter @opennotes/ui dev         # watch mode
pnpm --filter @opennotes/ui type-check  # tsc --noEmit
pnpm --filter @opennotes/ui test        # vitest
```

### Builder choice — tsup

We picked `tsup` over vite lib mode because:

- The scaffold has no JSX yet, so the Solid Babel transform is not required to produce working output.
- `tsup` is a single dev dependency vs. `vite` + `vite-plugin-solid` and does not need a project-level `vite.config.ts`.
- `tsconfig.json` uses `jsx: preserve` with `jsxImportSource: "solid-js"`; `tsup`/esbuild is configured to preserve JSX (`esbuildOptions.jsx = "preserve"`) so downstream consumers run their own Solid transform through `vite-plugin-solid`.
- `solid-js`, `@kobalte/core`, `class-variance-authority`, `clsx`, and `tailwind-merge` are marked `external` so the single-instance invariant is preserved.

If a future subtask (e.g. .05 or .06) lands a component whose JSX tsup cannot preserve cleanly, fall back to `vite` lib mode with [`vite-plugin-solid`](https://github.com/solidjs/vite-plugin-solid) (the playground already uses `vite-plugin-solid@^2.11`). Swap `tsup.config.ts` for `vite.config.ts` with `build.lib`, keep the same `external` list, and update the `build`/`dev` scripts.

## Constraints

- ESM only. No CJS build.
- Source under `src/` uses relative imports or bare specifiers; no `~/...` or `@playground/...` aliases so the code compiles unchanged from any sibling package.
- `solid-js` and `@kobalte/core` are `peerDependencies`, not regular dependencies. They are listed under `devDependencies` solely for local type-checking.
