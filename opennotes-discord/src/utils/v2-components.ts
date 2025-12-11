import {
  MessageFlags,
  ContainerBuilder,
  SectionBuilder,
  SeparatorBuilder,
  TextDisplayBuilder,
  ThumbnailBuilder,
  SeparatorSpacingSize,
  MediaGalleryBuilder,
  MediaGalleryItemBuilder,
  type ButtonBuilder,
} from 'discord.js';

/**
 * Color constants for Components v2 accent colors.
 * Use with ContainerBuilder.setAccentColor() to set visual urgency indicators.
 *
 * @example
 * // Set critical urgency color on a container
 * const container = new ContainerBuilder()
 *   .setAccentColor(V2_COLORS.CRITICAL);
 *
 * // Migration from v1 embeds:
 * // Old: new EmbedBuilder().setColor(0xED4245)
 * // New: createContainer(V2_COLORS.CRITICAL)
 */
export const V2_COLORS = {
  CRITICAL: 0xed4245,
  HIGH: 0xffa500,
  MEDIUM: 0xfee75c,
  COMPLETE: 0x5865f2,

  HELPFUL: 0x57f287,
  NOT_HELPFUL: 0xed4245,
  PENDING: 0x5865f2,
  RATED: 0x9b59b6,

  INFO: 0x3498db,
  PRIMARY: 0x5865f2,
} as const;

/**
 * Emoji icons for Components v2 visual indicators.
 * Use in TextDisplayBuilder content for consistent visual language.
 *
 * @example
 * // Add urgency indicator to text
 * new TextDisplayBuilder()
 *   .setContent(`${V2_ICONS.CRITICAL} **Needs Attention**`);
 *
 * // Show confidence level
 * const icon = ratingCount >= 5 ? V2_ICONS.STANDARD : V2_ICONS.PROVISIONAL;
 */
export const V2_ICONS = {
  CRITICAL: '\u{1F534}',
  HIGH: '\u{1F7E0}',
  MEDIUM: '\u{1F7E1}',
  COMPLETE: '\u{1F535}',

  HELPFUL: '\u2705',
  NOT_HELPFUL: '\u274C',
  PENDING: '\u{1F50E}',
  RATED: '\u{1F5F3}\uFE0F',

  STANDARD: '\u2B50',
  PROVISIONAL: '\u{1F535}',
  NO_DATA: '\u2B55',
} as const;

/**
 * Discord API limits for Components v2.
 * Use these constants to validate component counts before sending.
 *
 * @example
 * // Validate container before sending
 * if (components.length > V2_LIMITS.MAX_COMPONENTS_PER_CONTAINER) {
 *   throw new Error('Too many components');
 * }
 */
export const V2_LIMITS = {
  MAX_COMPONENTS_PER_CONTAINER: 40,
  MAX_TEXT_DISPLAY_LENGTH: 4000,
  MAX_ACTION_ROWS: 5,
  MAX_NOTES_PER_QUEUE_PAGE: 4,
} as const;

/**
 * Urgency classification levels for note rating progress.
 */
export type UrgencyLevel = 'critical' | 'high' | 'medium';

/**
 * Result of urgency calculation containing level, color, and emoji.
 */
export interface UrgencyResult {
  urgencyLevel: UrgencyLevel;
  urgencyColor: number;
  urgencyEmoji: string;
}

/**
 * Input parameters for progress formatting.
 */
export interface ProgressInput {
  ratingCount: number;
  ratingTarget: number;
  raterCount: number;
  raterTarget: number;
}

/**
 * Calculates urgency level based on rating progress.
 * Returns urgency classification with corresponding color and emoji for visual indicators.
 *
 * @param ratingCount - Current number of ratings received
 * @param minRatingsNeeded - Minimum ratings needed for completion
 * @returns Urgency level, color (for container accent), and emoji (for text display)
 *
 * @example
 * // Note with no ratings is critical
 * const urgency = calculateUrgency(0, 5);
 * console.log(urgency.urgencyLevel); // 'critical'
 *
 * // Use with container
 * const container = createContainer(urgency.urgencyColor);
 *
 * // Use emoji in text
 * new TextDisplayBuilder()
 *   .setContent(`${urgency.urgencyEmoji} Note needs ratings`);
 */
export function calculateUrgency(
  ratingCount: number,
  minRatingsNeeded: number
): UrgencyResult {
  if (ratingCount === 0) {
    return {
      urgencyLevel: 'critical',
      urgencyColor: V2_COLORS.CRITICAL,
      urgencyEmoji: V2_ICONS.CRITICAL,
    };
  }

  if (ratingCount < Math.floor(minRatingsNeeded / 2)) {
    return {
      urgencyLevel: 'high',
      urgencyColor: V2_COLORS.HIGH,
      urgencyEmoji: V2_ICONS.HIGH,
    };
  }

  return {
    urgencyLevel: 'medium',
    urgencyColor: V2_COLORS.MEDIUM,
    urgencyEmoji: V2_ICONS.MEDIUM,
  };
}

/**
 * Formats progress information as a multi-line markdown string.
 * Displays rating count, percentage, and unique rater count.
 *
 * @param progress - Object containing rating and rater counts and targets
 * @returns Formatted markdown string with progress statistics
 *
 * @example
 * const progressText = formatProgress({
 *   ratingCount: 3,
 *   ratingTarget: 5,
 *   raterCount: 2,
 *   raterTarget: 3,
 * });
 * // Returns:
 * // **Progress**: 3/5 ratings (60%)
 * // **Raters**: 2/3 unique raters
 *
 * // Use in a section
 * createTextSection(progressText);
 */
export function formatProgress(progress: ProgressInput): string {
  const { ratingCount, ratingTarget, raterCount, raterTarget } = progress;
  const percent =
    ratingTarget > 0 ? Math.round((ratingCount / ratingTarget) * 100) : 0;

  return [
    `**Progress**: ${ratingCount}/${ratingTarget} ratings (${percent}%)`,
    `**Raters**: ${raterCount}/${raterTarget} unique raters`,
  ].join('\n');
}

/**
 * Creates a visual progress bar using Unicode block characters.
 * Returns a monospace-formatted string suitable for Discord display.
 *
 * @param current - Current progress value
 * @param max - Maximum progress value (must be > 0 for meaningful display)
 * @param width - Width of the bar in characters (default: 10, must be > 0)
 * @returns Monospace-formatted progress bar string
 * @throws Error if width is not greater than 0
 *
 * @example
 * // Create a 50% progress bar
 * const bar = formatProgressBar(5, 10);
 * // Returns: `█████░░░░░`
 *
 * // Custom width
 * const wideBar = formatProgressBar(3, 10, 20);
 * // Returns: `██████░░░░░░░░░░░░░░`
 *
 * // Use in text display
 * new TextDisplayBuilder()
 *   .setContent(`Progress: ${formatProgressBar(3, 5)}`);
 */
export function formatProgressBar(
  current: number,
  max: number,
  width: number = 10
): string {
  if (width <= 0) {
    throw new Error('width must be greater than 0');
  }
  const ratio = max > 0 ? current / max : 0;
  const filled = Math.round(ratio * width);
  const empty = width - filled;
  return '`' + '\u2588'.repeat(filled) + '\u2591'.repeat(empty) + '`';
}

/**
 * Formats a confidence indicator based on rating count.
 * Returns an emoji and label indicating data reliability.
 *
 * @param ratingCount - Number of ratings received
 * @returns Formatted string with confidence icon and label
 *
 * @example
 * formatConfidence(5);  // Returns: "⭐ Standard"
 * formatConfidence(3);  // Returns: "🔵 Provisional"
 * formatConfidence(0);  // Returns: "⭕ No data"
 *
 * // Use in metadata section
 * createTextSection(`Confidence: ${formatConfidence(ratingCount)}`);
 */
export function formatConfidence(ratingCount: number): string {
  if (ratingCount >= 5) {
    return `${V2_ICONS.STANDARD} Standard`;
  }
  if (ratingCount > 0) {
    return `${V2_ICONS.PROVISIONAL} Provisional`;
  }
  return `${V2_ICONS.NO_DATA} No data`;
}

/**
 * Escapes Discord markdown special characters in text.
 * Use to prevent unintended formatting when displaying user content.
 *
 * @param text - Text that may contain markdown characters
 * @returns Text with markdown characters escaped
 *
 * @example
 * sanitizeMarkdown('*bold* _italic_');
 * // Returns: '\*bold\* \_italic\_'
 *
 * // Safe display of user content
 * const safeContent = sanitizeMarkdown(userInput);
 * createTextSection(safeContent);
 */
export function sanitizeMarkdown(text: string): string {
  return text.replace(/([*_`~|>\\])/g, '\\$1');
}

/**
 * Truncates text to a maximum length, adding ellipsis if truncated.
 * Ensures the result never exceeds maxLength including ellipsis.
 *
 * @param text - Text to truncate
 * @param maxLength - Maximum length of result (must be >= 3 to accommodate ellipsis)
 * @returns Original text if shorter than maxLength, otherwise truncated with "..."
 * @throws Error if maxLength is less than 3
 *
 * @example
 * truncate('Hello World', 8);  // Returns: 'Hello...'
 * truncate('Hi', 10);          // Returns: 'Hi'
 * truncate('Hello', 3);        // Returns: '...'
 *
 * // Truncate note content for preview
 * const preview = truncate(note.content, 200);
 * createTextSection(preview);
 */
export function truncate(text: string, maxLength: number): string {
  if (maxLength < 3) {
    throw new Error('maxLength must be at least 3');
  }
  if (text.length <= maxLength) {
    return text;
  }
  return text.substring(0, maxLength - 3) + '...';
}

/**
 * Options for v2MessageFlags helper.
 */
export interface V2MessageFlagsOptions {
  ephemeral?: boolean;
}

/**
 * Creates message flags for Components v2 messages.
 * Always includes IsComponentsV2 flag, optionally adds Ephemeral.
 *
 * @param options - Optional settings (ephemeral: boolean)
 * @returns Combined message flags as a number
 *
 * @example
 * // Public Components v2 message
 * await interaction.reply({
 *   components: [container],
 *   flags: v2MessageFlags(),
 * });
 *
 * // Ephemeral Components v2 message
 * await interaction.reply({
 *   components: [container],
 *   flags: v2MessageFlags({ ephemeral: true }),
 * });
 *
 * // Migration from v1:
 * // Old: flags: MessageFlags.Ephemeral
 * // New: flags: v2MessageFlags({ ephemeral: true })
 */
export function v2MessageFlags(options: V2MessageFlagsOptions = {}): number {
  let flags = MessageFlags.IsComponentsV2;
  if (options.ephemeral) {
    flags = flags | MessageFlags.Ephemeral;
  }
  return flags;
}

/**
 * Creates a SeparatorBuilder with small spacing.
 * Use for subtle visual breaks between content sections.
 *
 * @returns SeparatorBuilder configured with small spacing
 *
 * @example
 * // Add subtle spacing between sections
 * container
 *   .addTextDisplayComponents(header)
 *   .addSeparatorComponents(createSmallSeparator())
 *   .addSectionComponents(content);
 *
 * // Migration from v1:
 * // Old: embed field with blank value
 * // New: createSmallSeparator()
 */
export function createSmallSeparator(): SeparatorBuilder {
  return new SeparatorBuilder().setSpacing(SeparatorSpacingSize.Small);
}

/**
 * Creates a SeparatorBuilder configured as a visual divider line.
 * Use for strong visual separation between major content sections.
 *
 * @returns SeparatorBuilder configured with divider=true
 *
 * @example
 * // Add divider before action buttons
 * container
 *   .addSectionComponents(content)
 *   .addSeparatorComponents(createDivider())
 *   .addActionRowComponents(buttons);
 *
 * // Migration from v1:
 * // Old: horizontal rule in description
 * // New: createDivider()
 */
export function createDivider(): SeparatorBuilder {
  return new SeparatorBuilder().setDivider(true);
}

/**
 * Creates a ContainerBuilder with an accent color.
 * The container is the root canvas for Components v2 messages.
 *
 * @param accentColor - Hex color value for the container's accent bar
 * @returns ContainerBuilder configured with the accent color
 *
 * @example
 * // Create container with urgency color
 * const urgency = calculateUrgency(0, 5);
 * const container = createContainer(urgency.urgencyColor);
 *
 * // Use predefined colors
 * const container = createContainer(V2_COLORS.CRITICAL);
 *
 * // Migration from v1:
 * // Old: new EmbedBuilder().setColor(0xED4245)
 * // New: createContainer(V2_COLORS.CRITICAL)
 */
export function createContainer(accentColor: number): ContainerBuilder {
  return new ContainerBuilder().setAccentColor(accentColor);
}

/**
 * Creates a TextDisplayBuilder with markdown content.
 * Use for simple text content without accessories.
 *
 * @param content - Markdown content for the text display
 * @returns TextDisplayBuilder with the text content
 *
 * @example
 * // Simple text
 * container.addTextDisplayComponents(
 *   createTextSection('**Note Content**\nThis is the note body.')
 * );
 *
 * // Migration from v1:
 * // Old: embed.setDescription('content')
 * // New: container.addTextDisplayComponents(createTextSection('content'))
 */
export function createTextSection(content: string): TextDisplayBuilder {
  return new TextDisplayBuilder().setContent(content);
}

/**
 * Creates a SectionBuilder with text content and a button accessory.
 * The button appears to the right of the text content.
 *
 * @param content - Markdown content for the text display
 * @param button - ButtonBuilder to use as the accessory
 * @returns SectionBuilder with text and button accessory
 *
 * @example
 * import { ButtonBuilder, ButtonStyle } from 'discord.js';
 *
 * const viewButton = new ButtonBuilder()
 *   .setCustomId('view_original')
 *   .setLabel('View Original')
 *   .setStyle(ButtonStyle.Link)
 *   .setURL('https://example.com');
 *
 * container.addSectionComponents(
 *   createTextWithButton('Note summary here...', viewButton)
 * );
 *
 * // Migration from v1:
 * // Old: separate embed + action row
 * // New: integrated section with button accessory
 */
export function createTextWithButton(
  content: string,
  button: ButtonBuilder
): SectionBuilder {
  return new SectionBuilder()
    .addTextDisplayComponents(new TextDisplayBuilder().setContent(content))
    .setButtonAccessory(button);
}

/**
 * Creates a SectionBuilder with text content and a thumbnail accessory.
 * The thumbnail appears to the right of the text content.
 *
 * @param content - Markdown content for the text display
 * @param thumbnailUrl - URL of the thumbnail image
 * @returns SectionBuilder with text and thumbnail accessory
 *
 * @example
 * // Section with author avatar
 * container.addSectionComponents(
 *   createTextWithThumbnail(
 *     '**Author**: @username\n**Created**: 2 hours ago',
 *     'https://cdn.discordapp.com/avatars/123/abc.png'
 *   )
 * );
 *
 * // Migration from v1:
 * // Old: embed.setThumbnail('url')
 * // New: createTextWithThumbnail('text', 'url')
 */
export function createTextWithThumbnail(
  content: string,
  thumbnailUrl: string
): SectionBuilder {
  return new SectionBuilder()
    .addTextDisplayComponents(new TextDisplayBuilder().setContent(content))
    .setThumbnailAccessory(
      new ThumbnailBuilder().setURL(thumbnailUrl)
    );
}

/**
 * Formats a status indicator with emoji and text.
 * Use for displaying healthy/unhealthy status in a consistent format.
 *
 * @param healthy - Whether the status is healthy/positive
 * @param label - Text label to display after the indicator
 * @returns Formatted string with status emoji and label
 *
 * @example
 * formatStatusIndicator(true, 'API');  // Returns: "OK API"
 * formatStatusIndicator(false, 'API'); // Returns: "Down API"
 *
 * // Use in status display
 * createTextSection(formatStatusIndicator(isHealthy, 'Database Connection'));
 */
export function formatStatusIndicator(healthy: boolean, label: string): string {
  return `${healthy ? V2_ICONS.HELPFUL : V2_ICONS.NOT_HELPFUL} ${label}`;
}

/**
 * Image URL pattern for detecting image URLs.
 * Supports common image formats with optional query parameters.
 */
const IMAGE_URL_PATTERN = /^https?:\/\/.+\.(jpg|jpeg|png|gif|webp)(\?.*)?$/i;

/**
 * Checks if a URL points to an image.
 *
 * @param url - URL to check
 * @returns true if the URL appears to be an image
 *
 * @example
 * isImageUrl('https://example.com/image.png'); // true
 * isImageUrl('https://example.com/page.html'); // false
 */
export function isImageUrl(url: string): boolean {
  return IMAGE_URL_PATTERN.test(url.trim());
}

/**
 * Creates a MediaGalleryBuilder from image URLs.
 * Use to embed images in v2 containers.
 *
 * @param imageUrls - Array of image URLs
 * @param maxImages - Maximum number of images to include (default 10)
 * @returns MediaGalleryBuilder with image items, or undefined if no valid images
 *
 * @example
 * const gallery = createMediaGallery(['https://example.com/img1.png', 'https://example.com/img2.png']);
 * if (gallery) {
 *   container.addMediaGalleryComponents(gallery);
 * }
 */
export function createMediaGallery(
  imageUrls: string[],
  maxImages: number = 10
): MediaGalleryBuilder | undefined {
  const validUrls = imageUrls.filter(url => isImageUrl(url)).slice(0, maxImages);

  if (validUrls.length === 0) {
    return undefined;
  }

  const gallery = new MediaGalleryBuilder();
  gallery.addItems(
    ...validUrls.map((url, index) =>
      new MediaGalleryItemBuilder()
        .setURL(url)
        .setDescription(`Image ${index + 1}`)
    )
  );

  return gallery;
}
