FROM node:22-slim AS builder

ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY

ENV CI=true

RUN corepack enable

WORKDIR /workspace

COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY opennotes-playground/package.json ./opennotes-playground/package.json
COPY opennotes-platform/package.json ./opennotes-platform/package.json
COPY opennotes-discord/package.json ./opennotes-discord/package.json
COPY packages/shared-types/package.json ./packages/shared-types/package.json
COPY packages/test-utils/package.json ./packages/test-utils/package.json
COPY packages/tokens/package.json ./packages/tokens/package.json
COPY packages/ui/package.json ./packages/ui/package.json

RUN pnpm install --frozen-lockfile --filter opennotes-playground...

COPY packages ./packages
COPY opennotes-playground ./opennotes-playground

RUN pnpm --filter opennotes-playground run build

FROM node:22-slim AS runtime

WORKDIR /app

COPY --from=builder /workspace/opennotes-playground/.output /app/.output

RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nodejs
USER nodejs

EXPOSE 8080

CMD ["node", ".output/server/index.mjs"]
