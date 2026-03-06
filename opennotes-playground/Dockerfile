FROM node:22-slim AS builder

RUN corepack enable pnpm

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM node:22-slim AS runtime

WORKDIR /app

COPY --from=builder /app/.output /app/.output

ENV PORT=8080
EXPOSE 8080

CMD ["node", ".output/server/index.mjs"]
