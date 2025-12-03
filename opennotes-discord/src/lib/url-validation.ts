export interface ImageUrlValidationResult {
  valid: boolean;
  url?: string;
  error?: string;
}

const ALLOWED_IMAGE_DOMAINS = new Set([
  'cdn.discordapp.com',
  'media.discordapp.net',
  'images-ext-1.discordapp.net',
  'images-ext-2.discordapp.net',
  'i.imgur.com',
  'imgur.com',
  'media.tenor.com',
  'tenor.com',
  'media.giphy.com',
  'giphy.com',
  'i.giphy.com',
  'pbs.twimg.com',
  'i.redd.it',
  'preview.redd.it',
  'external-preview.redd.it',
  'i.reddituploads.com',
  'upload.wikimedia.org',
]);

const ALLOWED_IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp']);

const MAX_URL_LENGTH = 2048;

const PRIVATE_IP_PATTERNS = [
  /^127\./,
  /^10\./,
  /^172\.(1[6-9]|2[0-9]|3[0-1])\./,
  /^192\.168\./,
  /^0\./,
  /^169\.254\./,
  /^::1$/,
  /^fc00:/i,
  /^fe80:/i,
];

export function isAllowedImageDomain(domain: string): boolean {
  const normalizedDomain = domain.toLowerCase();
  return ALLOWED_IMAGE_DOMAINS.has(normalizedDomain);
}

function isPrivateIpOrLocalhost(hostname: string): boolean {
  const lowerHost = hostname.toLowerCase();

  if (lowerHost === 'localhost' || lowerHost === 'localhost.localdomain') {
    return true;
  }

  for (const pattern of PRIVATE_IP_PATTERNS) {
    if (pattern.test(hostname)) {
      return true;
    }
  }

  const ipv4Pattern = /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/;
  if (ipv4Pattern.test(hostname)) {
    return true;
  }

  return false;
}

function hasControlCharacters(str: string): boolean {
  // eslint-disable-next-line no-control-regex -- Intentionally checking for control characters in URLs
  const controlCharPattern = /[\x00-\x1f\x7f]/;
  return controlCharPattern.test(str);
}

function hasEncodedDomain(url: string): boolean {
  const domainPart = url.replace(/^https?:\/\//, '').split('/')[0];
  return domainPart.includes('%');
}

export function sanitizeImageUrl(urlString: string): ImageUrlValidationResult {
  if (!urlString || urlString.trim().length === 0) {
    return { valid: false, error: 'URL cannot be empty' };
  }

  const trimmedUrl = urlString.trim();

  if (trimmedUrl === 'null' || trimmedUrl === 'undefined') {
    return { valid: false, error: 'Invalid URL value' };
  }

  if (hasControlCharacters(trimmedUrl)) {
    return { valid: false, error: 'URL contains invalid control characters' };
  }

  if (trimmedUrl.length > MAX_URL_LENGTH) {
    return { valid: false, error: `URL exceeds maximum length of ${MAX_URL_LENGTH} characters` };
  }

  if (hasEncodedDomain(trimmedUrl)) {
    return { valid: false, error: 'URL contains encoded characters in domain' };
  }

  let parsedUrl: URL;
  try {
    parsedUrl = new URL(trimmedUrl);
  } catch {
    return { valid: false, error: 'Invalid URL format' };
  }

  const protocol = parsedUrl.protocol.toLowerCase();
  if (protocol !== 'https:') {
    if (protocol === 'http:') {
      return { valid: false, error: 'Only HTTPS URLs are allowed' };
    }
    return { valid: false, error: `Invalid protocol: ${protocol}` };
  }

  if (parsedUrl.username || parsedUrl.password) {
    return { valid: false, error: 'URLs with embedded credentials are not allowed' };
  }

  const hostname = parsedUrl.hostname.toLowerCase();

  if (isPrivateIpOrLocalhost(hostname)) {
    return { valid: false, error: 'Private IP addresses and localhost are not allowed' };
  }

  if (!isAllowedImageDomain(hostname)) {
    return { valid: false, error: `Domain not in allowed list: ${hostname}` };
  }

  const pathname = parsedUrl.pathname.toLowerCase();
  const hasImageExtension = Array.from(ALLOWED_IMAGE_EXTENSIONS).some(ext =>
    pathname.endsWith(ext)
  );

  if (!hasImageExtension) {
    const pathWithoutQuery = pathname.split('?')[0];
    const extensionMatch = pathWithoutQuery.match(/\.[a-z0-9]+$/i);
    if (!extensionMatch || !ALLOWED_IMAGE_EXTENSIONS.has(extensionMatch[0].toLowerCase())) {
      return { valid: false, error: 'URL does not have a valid image extension' };
    }
  }

  const normalizedUrl = parsedUrl.toString();

  return {
    valid: true,
    url: normalizedUrl,
  };
}

export function extractAndSanitizeImageUrl(text: string): string | undefined {
  const imageUrlPattern = /https?:\/\/[^\s]+\.(?:png|jpg|jpeg|gif|webp)(?:\?[^\s]*)?/i;
  const match = text.match(imageUrlPattern);

  if (!match) {
    return undefined;
  }

  const result = sanitizeImageUrl(match[0]);
  return result.valid ? result.url : undefined;
}
