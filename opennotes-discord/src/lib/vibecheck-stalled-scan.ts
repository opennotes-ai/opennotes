import { cache } from '../cache.js';

export interface StalledScanRecord {
  scanId: string;
  initiatorId: string;
  guildId: string;
  days: number;
  source: 'slash_command' | 'prompt';
  notificationState?: 'pending' | 'sent';
  notifiedAt?: string;
}

const STALLED_SCAN_TTL_SECONDS = 7 * 24 * 60 * 60;

export function getStalledScanCacheKey(scanId: string): string {
  return `vibecheck:stalled:${scanId}`;
}

export async function getStalledScan(scanId: string): Promise<StalledScanRecord | null> {
  return cache.get<StalledScanRecord>(getStalledScanCacheKey(scanId));
}

export async function recordStalledScan(record: StalledScanRecord): Promise<void> {
  await cache.set(
    getStalledScanCacheKey(record.scanId),
    {
      ...record,
      notificationState: record.notificationState ?? 'pending',
    },
    STALLED_SCAN_TTL_SECONDS
  );
}

export async function clearStalledScan(scanId: string): Promise<void> {
  await cache.delete(getStalledScanCacheKey(scanId));
}

export async function markStalledScanNotified(scanId: string): Promise<boolean> {
  const stalledScan = await getStalledScan(scanId);
  if (!stalledScan) {
    return false;
  }

  await cache.set(
    getStalledScanCacheKey(scanId),
    {
      ...stalledScan,
      notificationState: 'sent',
      notifiedAt: new Date().toISOString(),
    },
    STALLED_SCAN_TTL_SECONDS
  );

  return true;
}
