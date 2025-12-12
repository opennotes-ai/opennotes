# Contributing to Open Notes

Thanks for your interest in contributing to Open Notes!

## Before You Start

**For larger changes**, please open a GitHub issue or reach out on [Discord](https://discord.gg/CsxBasRrte) first. This helps avoid duplication of effort or conflicts with work already in progress.

## Getting Started

1. Fork the repository
2. Clone and initialize submodules:
   ```console
   git clone <your-fork-url>
   cd opennotes
   git submodule update --init --recursive
   ```
3. Create a branch from `main`
4. Make your changes
5. Submit a pull request

## Development

### Server (Python/FastAPI)

```console
cd opennotes-server
uv sync --extra scoring
uv run pytest                    # Run tests
uv run ruff check . && uv run ruff format .  # Lint and format
uv run basedpyright src/         # Type check
```

### Discord Bot (TypeScript)

```console
cd opennotes-discord
pnpm install
pnpm test        # Run tests
pnpm run lint    # Lint
pnpm run build   # Build
```

## Security

Please report security vulnerabilities privately to security@opennotes.ai. Do not open public issues for security concerns.

## License

Contributions are accepted under the [MIT License](LICENSE).

## Questions?

- Open a [GitHub issue](https://github.com/opennotes-ai/opennotes/issues)
- Join our [Discord](https://discord.gg/CsxBasRrte)
