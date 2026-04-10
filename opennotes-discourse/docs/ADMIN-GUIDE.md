# OpenNotes for Discourse -- Admin Guide

This guide covers installing, configuring, and managing the OpenNotes plugin on your Discourse instance.

## Prerequisites

- A running [OpenNotes server](https://github.com/opennotes-ai/opennotes) instance
- An API key from the OpenNotes server (service account level)
- Discourse admin access

## Installation

Install the plugin by adding it to your Discourse `app.yml`:

```yaml
hooks:
  after_code:
    - exec:
        cd: $home/plugins
        cmd:
          - git clone https://github.com/opennotes-ai/opennotes.git opennotes-discourse
```

Rebuild your container:

```bash
./launcher rebuild app
```

## Configuration

After installation, go to **Admin > Settings > Plugins > OpenNotes**.

### Required Settings

| Setting | Description |
|---------|-------------|
| `opennotes_enabled` | Master switch for the plugin |
| `opennotes_server_url` | URL of your OpenNotes server (e.g., `https://api.opennotes.ai`) |
| `opennotes_api_key` | Service account API key from the OpenNotes server |

### Content Monitoring

| Setting | Description |
|---------|-------------|
| `opennotes_monitored_categories` | Comma-separated list of category names to monitor for content classification |

Posts in monitored categories are automatically sent to the OpenNotes server for classification. Posts in other categories are not scanned.

### Moderation Behavior

| Setting | Default | Description |
|---------|---------|-------------|
| `opennotes_auto_hide_on_consensus` | `false` | Automatically hide posts when community consensus says a moderation note is helpful |
| `opennotes_staff_approval_required` | `true` | Require staff approval before automated actions take effect |
| `opennotes_route_flags_to_community` | `true` | Send user flags to OpenNotes for community review instead of only the staff flag queue |

### Review Participation

| Setting | Default | Description |
|---------|---------|-------------|
| `opennotes_reviewer_min_trust_level` | `2` (Member) | Minimum Discourse trust level required to vote on moderation notes |

Trust level mapping:
- **TL0** (New): Cannot participate in reviews
- **TL1** (Basic): Cannot participate in reviews (default)
- **TL2** (Member): Can vote on notes (default threshold)
- **TL3** (Regular): Can vote on notes
- **TL4** (Leader): Can vote on notes

## How It Works

### Two-Tier Moderation

The plugin uses a two-tier approach:

**Tier 1 -- Automated action.** When the AI classifies content with high confidence as harmful, it acts immediately (e.g., hiding the post). A retroactive review note is created so the community can confirm or overturn the decision.

**Tier 2 -- Community review.** When confidence is lower, the post stays visible but enters the community review queue. Community members vote on whether action is needed, using a bridging-based algorithm that favors cross-perspective consensus.

### What Staff See

- **Review queue** (`/review`): Flagged items with classification labels, scores, and community vote tallies
- **Admin dashboard**: Activity metrics, classification breakdown, consensus health, top reviewers
- **Per-category config**: Different thresholds and review group routing per category

### Overturn Flow

If the community votes to overturn an automated action:
1. The post is restored
2. The post is marked scan-exempt (minor edits won't re-trigger classification)
3. A staff annotation is added explaining the post was hidden and restored
4. Substantial edits clear the exemption and allow re-classification

## Per-Category Configuration

Each monitored category can have its own settings:

- **Auto-action threshold**: How confident the AI needs to be before acting automatically (e.g., 0.90 for general discussion, 0.80 for announcements)
- **Review group routing**: Which trust level groups see review items from this category (e.g., staff-only for sensitive categories, community-wide for general)
- **Label routing**: Map specific classification labels to different review groups

## Webhooks

The plugin registers a webhook with the OpenNotes server during setup. When community consensus is reached on a note, the server sends a webhook to Discourse to execute the agreed-upon action.

As a fallback, the plugin also polls the server periodically to catch any missed webhook deliveries.

## Troubleshooting

**Posts not being classified:** Check that `opennotes_enabled` is true, the category is in `opennotes_monitored_categories`, and the server URL and API key are correct.

**Community review page empty:** Verify the logged-in user meets the `opennotes_reviewer_min_trust_level` threshold and that there are pending review items.

**Actions not being applied:** Check that `opennotes_auto_hide_on_consensus` is enabled or that staff are processing items in the review queue. If `opennotes_staff_approval_required` is true, automated actions need staff confirmation.
