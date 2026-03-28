# discourse-opennotes

A thin adapter plugin that connects Discourse to the OpenNotes community moderation system. Posts flagged by community members are routed through OpenNotes for consensus-based review, with results surfaced back into Discourse as context notes and moderation actions.

## Quick Start

```bash
mise run discourse:bootstrap
mise run discourse:up
```

Open Discourse at http://localhost:4200 and log in with the default admin credentials.

### Default Credentials

- Email: `admin@opennotes.local`
- Password: `opennotes-dev-password`

### Ports

| Service            | URL                    |
| ------------------ | ---------------------- |
| Discourse          | http://localhost:4200  |
| OpenNotes Server   | http://localhost:8000  |

## Plugin Development Workflow

1. Edit plugin files under `opennotes-discourse/plugin/`.
2. Restart the Discourse container to pick up changes:
   ```bash
   mise run discourse:down && mise run discourse:up
   ```
3. Refresh Discourse in your browser.

For JavaScript/template changes, Discourse's Ember live-reload may pick them up automatically. Server-side Ruby changes always require a container restart.

## Directory Structure

```
opennotes-discourse/
  plugin/                   # Discourse plugin source (mounted into container)
    plugin.rb               # Plugin entry point (name, version, initialization)
    config/
      settings.yml          # Site settings (API URL, trust levels, feature flags)
      locales/
        server.en.yml       # Server-side translations
        client.en.yml       # Client-side translations
  docker/
    bootstrap.sh            # One-time dev environment setup
    .gitignore              # Ignores cloned Discourse repo
    scripts/
      wait-for-discourse.sh # Health-check polling script
  tests/
    e2e/
      fixtures/             # Test data and seed fixtures
      helpers/              # Shared test utilities
      specs/                # Playwright test specs
```

## Testing

Run end-to-end tests with Playwright:

```bash
mise run discourse:test:e2e
```

## Troubleshooting

### Docker memory

Discourse requires significant memory to run. Allocate at least 4 GB to Docker Desktop (Settings > Resources > Memory). 6 GB or more is recommended.

### Port conflicts

If port 4200 is already in use, stop any other Discourse or Ember processes before starting the dev container.

### M1/ARM compatibility

The Discourse dev image supports ARM64. If you see image pull errors, ensure Docker Desktop is updated to the latest version and that Rosetta emulation is enabled if needed.

### Plugin not showing in admin

1. Verify the symlink exists and points to the correct path:
   ```bash
   ls -la docker/.discourse/plugins/discourse-opennotes
   ```
   It should point to `../../../` (the plugin root).

2. Restart the container:
   ```bash
   mise run discourse:down && mise run discourse:up
   ```

3. Check the Discourse container logs for plugin load errors:
   ```bash
   docker logs discourse-dev
   ```
