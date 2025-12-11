# Components v2 UI Design Patterns

Design document for migrating note cards and queue items to Discord Components v2.

## Overview

This document defines visual patterns and reusable templates for displaying notes and queue items using Discord's Components v2 system (ContainerBuilder, SectionBuilder, etc.).

## Key Components

| Component | Purpose | Use Case |
|-----------|---------|----------|
| `ContainerBuilder` | Root canvas with accent color | Note cards, queue summaries |
| `SectionBuilder` | Groups text + optional accessory | Content sections, metadata |
| `TextDisplayBuilder` | Rich markdown text | Titles, descriptions, stats |
| `SeparatorBuilder` | Visual dividers | Section breaks |
| `MediaGalleryBuilder` | Multiple images (up to 10) | Notes with attachments |
| `ActionRowBuilder` | Button groups | Rating buttons, pagination |

## Color Palette

### Urgency Colors (Container Accent)

| Urgency | Hex | Sample | Emoji | Condition |
|---------|-----|--------|-------|-----------|
| Critical | `0xED4245` | <span style="display:inline-block;width:40px;height:16px;background-color:#ED4245;border-radius:3px;vertical-align:middle;"></span> | 🔴 | 0 ratings |
| High | `0xFFA500` | <span style="display:inline-block;width:40px;height:16px;background-color:#FFA500;border-radius:3px;vertical-align:middle;"></span> | 🟠 | <50% of min ratings |
| Medium | `0xFEE75C` | <span style="display:inline-block;width:40px;height:16px;background-color:#FEE75C;border-radius:3px;vertical-align:middle;"></span> | 🟡 | ≥50% of min ratings |
| Complete | `0x5865F2` | <span style="display:inline-block;width:40px;height:16px;background-color:#5865F2;border-radius:3px;vertical-align:middle;"></span> | 🔵 | At threshold |

### Note Status Colors

| Status | Hex | Sample | Emoji | Meaning |
|--------|-----|--------|-------|---------|
| Pending | `0x5865F2` | <span style="display:inline-block;width:40px;height:16px;background-color:#5865F2;border-radius:3px;vertical-align:middle;"></span> | 🔎 | Awaiting ratings |
| Helpful | `0x57F287` | <span style="display:inline-block;width:40px;height:16px;background-color:#57F287;border-radius:3px;vertical-align:middle;"></span> | ✅ | Published |
| Not Helpful | `0xED4245` | <span style="display:inline-block;width:40px;height:16px;background-color:#ED4245;border-radius:3px;vertical-align:middle;"></span> | ❌ | Rejected |
| Rated | `0x9B59B6` | <span style="display:inline-block;width:40px;height:16px;background-color:#9B59B6;border-radius:3px;vertical-align:middle;"></span> | 🗳️ | User's rated notes |

### Constants

```typescript
export const V2_COLORS = {
  // Urgency
  CRITICAL: 0xED4245,
  HIGH: 0xFFA500,
  MEDIUM: 0xFEE75C,
  COMPLETE: 0x5865F2,

  // Note Status
  HELPFUL: 0x57F287,
  NOT_HELPFUL: 0xED4245,
  PENDING: 0x5865F2,
  RATED: 0x9B59B6,

  // General
  INFO: 0x3498DB,
  PRIMARY: 0x5865F2,
} as const;

export const V2_ICONS = {
  // Urgency
  CRITICAL: '🔴',
  HIGH: '🟠',
  MEDIUM: '🟡',
  COMPLETE: '🔵',

  // Note Status
  HELPFUL: '✅',
  NOT_HELPFUL: '❌',
  PENDING: '🔎',
  RATED: '🗳️',

  // Confidence
  STANDARD: '⭐',
  PROVISIONAL: '🔵',
  NO_DATA: '⭕',
} as const;
```

## Note Card Layout

### Structure

```
ContainerBuilder (accent = urgency color)
├── TextDisplayBuilder (title with urgency emoji)
├── SeparatorBuilder (small)
├── SectionBuilder (content)
│   ├── TextDisplayBuilder (note summary)
│   └── ButtonAccessory (optional: "View Original")
├── MediaGalleryBuilder (if note has images/videos, up to 10)
├── SeparatorBuilder (small)
├── SectionBuilder (metadata)
│   ├── TextDisplayBuilder (progress stats)
│   └── ThumbnailAccessory (optional: author avatar)
├── SeparatorBuilder (divider=true)
└── ActionRowBuilder (rating buttons)
```

### Code Example

```typescript
import {
  ContainerBuilder,
  SectionBuilder,
  TextDisplayBuilder,
  SeparatorBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  SeparatorSpacingSize,
  MessageFlags,
} from 'discord.js';

function buildNoteCard(note: NoteData, progress: NoteProgress): ContainerBuilder {
  return new ContainerBuilder()
    .setAccentColor(progress.urgencyColor)
    .addTextDisplayComponents(
      new TextDisplayBuilder()
        .setContent(`${progress.urgencyEmoji} **Note #${note.id}**`)
    )
    .addSeparatorComponents(
      new SeparatorBuilder().setSpacing(SeparatorSpacingSize.Small)
    )
    .addSectionComponents(
      new SectionBuilder()
        .addTextDisplayComponents(
          new TextDisplayBuilder()
            .setContent(truncate(note.summary, 500))
        )
    )
    .addSeparatorComponents(
      new SeparatorBuilder().setSpacing(SeparatorSpacingSize.Small)
    )
    .addSectionComponents(
      new SectionBuilder()
        .addTextDisplayComponents(
          new TextDisplayBuilder()
            .setContent(formatProgress(progress)),
          new TextDisplayBuilder()
            .setContent(formatMetadata(note))
        )
    )
    .addSeparatorComponents(
      new SeparatorBuilder().setDivider(true)
    )
    .addActionRowComponents(
      buildRatingButtons(note.id)
    );
}
```

## Rating Button Patterns

### Active State (Awaiting Rating)

```typescript
function buildRatingButtons(noteId: string, isAdmin: boolean = false): ActionRowBuilder<ButtonBuilder> {
  const row = new ActionRowBuilder<ButtonBuilder>()
    .addComponents(
      new ButtonBuilder()
        .setCustomId(`rate:${noteId}:helpful`)
        .setLabel('Helpful')
        .setStyle(ButtonStyle.Success),
      new ButtonBuilder()
        .setCustomId(`rate:${noteId}:not_helpful`)
        .setLabel('Not Helpful')
        .setStyle(ButtonStyle.Danger)
    );

  if (isAdmin) {
    row.addComponents(
      new ButtonBuilder()
        .setCustomId(`force_publish:${noteId}`)
        .setLabel('Force Publish')
        .setStyle(ButtonStyle.Danger)
    );
  }

  return row;
}
```

### Disabled State (After Rating)

```typescript
function buildRatedButton(noteId: string, helpful: boolean): ActionRowBuilder<ButtonBuilder> {
  return new ActionRowBuilder<ButtonBuilder>()
    .addComponents(
      new ButtonBuilder()
        .setCustomId(`rated:${noteId}`)
        .setLabel(helpful ? 'Rated Helpful' : 'Rated Not Helpful')
        .setStyle(helpful ? ButtonStyle.Success : ButtonStyle.Danger)
        .setDisabled(true)
    );
}
```

### Button Accessory (Single Action)

Use for contextual single-button actions within a section:

```typescript
new SectionBuilder()
  .addTextDisplayComponents(
    new TextDisplayBuilder().setContent('**Original Message**\n> ' + messageContent)
  )
  .setButtonAccessory(
    new ButtonBuilder()
      .setStyle(ButtonStyle.Link)
      .setLabel('Jump to Message')
      .setURL(messageUrl)
  )
```

## Progress Indicators

### Rating Progress

```typescript
function formatProgress(progress: NoteProgress): string {
  const { ratingCount, ratingTarget, raterCount, raterTarget } = progress;
  const percent = Math.round((ratingCount / ratingTarget) * 100);

  return [
    `**Progress**: ${ratingCount}/${ratingTarget} ratings (${percent}%)`,
    `**Raters**: ${raterCount}/${raterTarget} unique raters`,
  ].join('\n');
}
```

### Visual Progress Bar (Optional)

```typescript
function formatProgressBar(current: number, max: number, width: number = 10): string {
  const filled = Math.round((current / max) * width);
  const empty = width - filled;
  return '`' + '█'.repeat(filled) + '░'.repeat(empty) + '`';
}

// Usage: formatProgressBar(3, 5) => "`██████░░░░`"
```

### Confidence Indicators

| Confidence | Emoji | Label | Condition |
|------------|-------|-------|-----------|
| Standard | `⭐` | "Standard (5+ ratings)" | ≥5 ratings |
| Provisional | `🔵` | "Provisional (<5 ratings)" | 1-4 ratings |
| No Data | `⭕` | "No data" | 0 ratings |

```typescript
function formatConfidence(ratingCount: number): string {
  if (ratingCount >= 5) return '⭐ Standard';
  if (ratingCount > 0) return '🔵 Provisional';
  return '⭕ No data';
}
```

## Queue Display Pattern

### Single-Message Compact Structure

All queue content fits in one ContainerBuilder message. Urgency is indicated via emoji in text (since container has single accent color). Limited to 4 notes per page due to Discord's 5 action row limit.

```
ContainerBuilder (accent = PRIMARY)
├── TextDisplayBuilder ("## 📋 Rating Queue")
├── TextDisplayBuilder ("3 notes need your rating")
├── TextDisplayBuilder ("🔴 1 critical • 🟠 1 high • 🟡 1 medium")
├── SeparatorBuilder (divider)
│
├── SectionBuilder (Note 1: 🔴 critical)
│   └── TextDisplayBuilder ("🔴 **Note #42**\nNote summary text...")
├── MediaGalleryBuilder (Note 1 images, if any)
├── ActionRowBuilder (Note 1 rating buttons)
├── SeparatorBuilder (small)
│
├── SectionBuilder (Note 2: 🟡 medium)
│   └── TextDisplayBuilder ("🟡 **Note #43**\nNote summary text...")
├── MediaGalleryBuilder (Note 2 images, if any)
├── ActionRowBuilder (Note 2 rating buttons)
├── SeparatorBuilder (small)
│
├── SectionBuilder (Note 3: 🟠 high)
│   └── TextDisplayBuilder ("🟠 **Note #44**\nNote summary text...")
├── MediaGalleryBuilder (Note 3 images, if any)
├── ActionRowBuilder (Note 3 rating buttons)
├── SeparatorBuilder (divider)
│
└── ActionRowBuilder (Pagination: ◀ | 1/3 | ▶)
```

**Constraints:**
- Max 4 notes per page (4 rating rows + 1 pagination row = 5 action rows)
- Single accent color for container (use emoji for per-note urgency)
- All interactions in one message (simpler state management)

### Queue Builder

```typescript
function buildQueueMessage(
  notes: NoteData[],
  stats: QueueStats,
  page: number,
  totalPages: number
): ContainerBuilder {
  const container = new ContainerBuilder()
    .setAccentColor(V2_COLORS.PRIMARY)
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent('## 📋 Rating Queue'),
      new TextDisplayBuilder().setContent(`**${stats.total}** notes need your rating`),
      new TextDisplayBuilder().setContent(
        `🔴 ${stats.critical} critical • 🟠 ${stats.high} high • 🟡 ${stats.medium} medium`
      )
    )
    .addSeparatorComponents(
      new SeparatorBuilder().setDivider(true)
    );

  // Add each note (max 4 per page)
  for (const note of notes.slice(0, 4)) {
    const urgency = calculateUrgency(note.ratingCount, note.minRatingsNeeded);

    container.addSectionComponents(
      new SectionBuilder()
        .addTextDisplayComponents(
          new TextDisplayBuilder().setContent(
            `${urgency.emoji} **Note #${note.id}**\n${truncate(note.summary, 200)}`
          )
        )
    );

    // Add media gallery if note has images/videos
    if (note.mediaUrls && note.mediaUrls.length > 0) {
      container.addMediaGalleryComponents(
        new MediaGalleryBuilder()
          .addItems(
            ...note.mediaUrls.slice(0, 10).map((url, i) =>
              new MediaGalleryItemBuilder()
                .setURL(url)
                .setDescription(`Media ${i + 1}`)
            )
          )
      );
    }

    container
      .addActionRowComponents(buildRatingButtons(note.id))
      .addSeparatorComponents(
        new SeparatorBuilder().setSpacing(SeparatorSpacingSize.Small)
      );
  }

  // Add pagination if needed
  if (totalPages > 1) {
    container
      .addSeparatorComponents(
        new SeparatorBuilder().setDivider(true)
      )
      .addActionRowComponents(buildPagination(page, totalPages));
  }

  return container;
}
```

### Pagination Buttons

```typescript
function buildPagination(page: number, totalPages: number): ActionRowBuilder<ButtonBuilder> {
  return new ActionRowBuilder<ButtonBuilder>()
    .addComponents(
      new ButtonBuilder()
        .setCustomId(`page:${page - 1}`)
        .setLabel('◀')
        .setStyle(ButtonStyle.Secondary)
        .setDisabled(page <= 1),
      new ButtonBuilder()
        .setCustomId('page:current')
        .setLabel(`${page}/${totalPages}`)
        .setStyle(ButtonStyle.Secondary)
        .setDisabled(true),
      new ButtonBuilder()
        .setCustomId(`page:${page + 1}`)
        .setLabel('▶')
        .setStyle(ButtonStyle.Secondary)
        .setDisabled(page >= totalPages)
    );
}
```

## Urgency Patterns

### Urgency Calculation

```typescript
interface NoteProgress {
  ratingCount: number;
  ratingTarget: number;
  raterCount: number;
  raterTarget: number;
  urgencyLevel: 'critical' | 'high' | 'medium';
  urgencyColor: number;
  urgencyEmoji: string;
}

function calculateUrgency(ratingCount: number, minRatingsNeeded: number): Pick<NoteProgress, 'urgencyLevel' | 'urgencyColor' | 'urgencyEmoji'> {
  if (ratingCount === 0) {
    return {
      urgencyLevel: 'critical',
      urgencyColor: V2_COLORS.CRITICAL,
      urgencyEmoji: '🔴',
    };
  }

  if (ratingCount < Math.floor(minRatingsNeeded / 2)) {
    return {
      urgencyLevel: 'high',
      urgencyColor: V2_COLORS.HIGH,
      urgencyEmoji: '🟠',
    };
  }

  return {
    urgencyLevel: 'medium',
    urgencyColor: V2_COLORS.MEDIUM,
    urgencyEmoji: '🟡',
  };
}
```

### Status Indicators

| Status | Display |
|--------|---------|
| Needs Ratings | `🔎 Awaiting More Ratings` |
| Helpful | `✅ Published` |
| Not Helpful | `❌ Not Helpful` |
| Force Published | `⚠️ Admin Published` |

## Media Gallery Usage

For notes with image attachments:

```typescript
function buildNoteWithImages(note: NoteData, imageUrls: string[]): ContainerBuilder {
  const container = new ContainerBuilder()
    .setAccentColor(getUrgencyColor(note));

  // Add note content first
  container.addTextDisplayComponents(
    new TextDisplayBuilder().setContent(`**Note #${note.id}**\n\n${note.summary}`)
  );

  // Add image gallery if images exist
  if (imageUrls.length > 0) {
    container.addMediaGalleryComponents(
      new MediaGalleryBuilder()
        .addItems(
          ...imageUrls.slice(0, 10).map((url, i) =>
            new MediaGalleryItemBuilder()
              .setURL(url)
              .setDescription(`Image ${i + 1}`)
          )
        )
    );
  }

  return container;
}
```

## Mobile Considerations

1. **Text Wrapping**: TextDisplayBuilder content wraps naturally on mobile
2. **Accent Color**: Renders as left border, visible on all screen sizes
3. **Button Limits**: Keep ActionRow to 3-4 buttons max (they stack on mobile)
4. **Thumbnail Size**: ThumbnailAccessory renders smaller on mobile
5. **Separator Visibility**: Dividers help visual scanning on narrow screens

## Sending V2 Messages

Components v2 messages require the `IsComponentsV2` flag:

```typescript
await interaction.reply({
  components: [noteCard.toJSON()],
  flags: MessageFlags.IsComponentsV2,
});

// For ephemeral v2 messages
await interaction.reply({
  components: [noteCard.toJSON()],
  flags: MessageFlags.IsComponentsV2 | MessageFlags.Ephemeral,
});
```

## Migration Checklist

### Completed
- [x] Create `QueueRendererV2` class with ContainerBuilder support
- [x] Create v2 component utilities (`v2-components.ts`)
- [x] Migrate `/list notes` to v2 (uses `QueueRendererV2`)
- [x] Migrate `/about-opennotes` to v2
- [x] Migrate `/status-bot` to v2 (`formatStatusSuccessV2`)
- [x] Migrate `/config` to v2
- [x] Migrate `/note write` modal and success displays to v2
- [x] Migrate context menu "Request Note" to v2
- [x] Migrate auto-post note publisher display to v2
- [x] Migrate guild onboarding DM to v2
- [x] Add `MessageFlags.IsComponentsV2` to migrated responses
- [x] Verify button interactions work with v2 containers
- [x] Update rating button handlers for new component structure
- [x] Add deprecation comments to v1 types (`QueueItem`, `QueueSummary`, `QueueRenderer`)
- [x] Add deprecation comments to v1 formatter methods

### Completed (V2 Migration)
- [x] Migrate `/list requests` to v2 (`formatListRequestsSuccessV2`)
- [x] Migrate `/list top-notes` to v2 (`formatTopNotesForQueueV2`)
- [x] Update error handling to use `formatErrorV2` in all commands
- [x] Remove v1 code paths (deprecated methods and classes removed)
- [ ] Test on mobile Discord client

### V1 Code Removed

The following deprecated v1 code has been removed:

**Types (`queue-renderer.ts`) - REMOVED:**
- `QueueItem` - Replaced by `QueueItemV2`
- `QueueSummary` - Replaced by `QueueSummaryV2`
- `QueueRenderer` - Replaced by `QueueRendererV2`

**Formatter Methods (`DiscordFormatter.ts`) - REMOVED:**
- `formatListRequestsSuccess` - Replaced by `formatListRequestsSuccessV2`
- `formatTopNotesForQueue` - Replaced by `formatTopNotesForQueueV2`
- `formatWriteNoteSuccess` - Replaced by `formatWriteNoteSuccessV2`
- `formatError` - Replaced by `formatErrorV2`

## References

- [Discord.js Components v2 Guide](https://discord.js.org/docs/packages/discord.js/14.25.1/ContainerBuilder:Class)
- [Discord API Components v2](https://discord.com/developers/docs/components/overview)
- Related tasks: task-823 (deprecation migration), task-825/826/827 (implementation)
