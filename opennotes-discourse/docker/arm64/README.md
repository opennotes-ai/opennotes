# ARM64 Discourse Dev Image

Native ARM64 build of `discourse/discourse_dev` for Apple Silicon Macs.

## Why

The official `discourse/discourse_dev:release` image is x86_64-only. Running it
on Apple Silicon requires QEMU emulation which is 5-10x slower (Ember CLI asset
compilation takes 3+ minutes vs seconds) and produces malformed HTTP headers that
break Playwright and Node.js HTTP clients.

This Dockerfile builds an equivalent image natively on ARM64. Same Ruby, Node,
PostgreSQL, and Redis versions. Same runit service manager. Compatible with
Discourse's `d/boot_dev` workflow.

## Usage

The bootstrap script auto-detects Apple Silicon and builds this image:

```bash
cd opennotes-discourse
mise run discourse:bootstrap
```

To build manually:

```bash
docker build -t discourse/discourse_dev:release docker/arm64
```

The image is tagged as `discourse/discourse_dev:release` so `d/boot_dev` picks
it up automatically (it skips `docker pull` on ARM and uses the local image).

## What's different from upstream

| Component | Upstream | ARM64 |
|---|---|---|
| Base image | `discourse/ruby:3.4.9-bookworm-slim` (x86_64) | `ruby:3.4.9-slim-bookworm` (multi-arch) |
| MailHog | `MailHog_linux_amd64` | `MailHog_linux_arm` (auto-detected) |
| ImageMagick | Custom build from source | Not included (install separately if needed) |
| nginx | Custom build from source | Not included (not needed for dev) |

Everything else (PostgreSQL 15, Redis, Node 22, pnpm 10, runit) is identical.

## Rebuilding

After Discourse updates Ruby or Node versions, update the `ARG` values at the
top of `Dockerfile` and rebuild:

```bash
docker build --no-cache -t discourse/discourse_dev:release docker/arm64
```
