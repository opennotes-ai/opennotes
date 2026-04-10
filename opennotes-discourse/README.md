# OpenNotes for Discourse

A Discourse plugin that adds AI-powered content moderation with community oversight to your forum.

When enabled, the plugin monitors categories you choose and classifies new posts automatically. Content the AI is confident is harmful gets acted on immediately. Everything else goes to a community review queue where members vote using a bridging-based consensus algorithm — the same approach used by Twitter/X Community Notes, where agreement across people who usually disagree carries more weight. Every automated decision can be reviewed and reversed.

**For forum administrators:** The plugin installs with a single line in your `app.yml`, connects to an OpenNotes server, and gives you per-category control over monitoring thresholds, review groups, and automation behavior. See the [Admin Guide](docs/ADMIN-GUIDE.md).

**For community members:** You'll see review banners on flagged posts and can participate in moderation decisions through a dedicated review page. No special setup needed — just meet the trust level your admin has configured. See the [User Guide](docs/USER-GUIDE.md).

## Development Quick Start

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

## API Key

The bootstrap script automatically provisions a Discourse API key and saves it to `docker/.discourse-api-key`. This key is used by the Playwright test harness for test data setup.

If you need to set it manually (e.g., for CI):

```bash
export DISCOURSE_API_KEY=<your-key>
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
   It should point to `../../../plugin` (the plugin source directory).

2. Restart the container:
   ```bash
   mise run discourse:down && mise run discourse:up
   ```

3. Check the Discourse container logs for plugin load errors:
   ```bash
   docker logs discourse_dev
   ```
