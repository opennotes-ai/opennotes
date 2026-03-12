import { cache } from '../cache.js';

export interface StalledScanRecord {
  scanId: string;
  initiatorId: string;
  guildId: string;
  days: number;
  source: 'slash_command' | 'prompt';
}

const STALLED_SCAN_TTL_SECONDS = 3600;

export function getStalledScanCacheKey(scanId: string): string {
  return `vibecheck:stalled:${scanId}`;
}

export async function getStalledScan(scanId: string): Promise<StalledScanRecord | null> {
  return cache.get<StalledScanRecord>(getStalledScanCacheKey(scanId));
}

export async function recordStalledScan(record: StalledScanRecord): Promise<void> {
  await cache.set(getStalledScanCacheKey(record.scanId), record, STALLED_SCAN_TTL_SECONDS);
}

export async function clearStalledScan(scanId: string): Promise<void> {
  await cache.delete(getStalledScanCacheKey(scanId));
}
