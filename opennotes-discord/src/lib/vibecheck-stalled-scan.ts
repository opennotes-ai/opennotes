import { cache } from '../cache.js';

export interface StalledScanRecord {
  scanId: string;
  initiatorId: string;
  guildId: string;
  days: number;
  source: 'slash_command' | 'prompt';
  notificationState?: 'pending' | 'sending' | 'sent' | 'failed_permanent';
  deliveryClaimedAt?: string;
  notifiedAt?: string;
  failedAt?: string;
  failureReason?: string;
}

const STALLED_SCAN_TTL_SECONDS = 7 * 24 * 60 * 60;
export const STALLED_SCAN_DELIVERY_CLAIM_TTL_MS = 60 * 1000;

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
      deliveryClaimedAt: undefined,
      notifiedAt: new Date().toISOString(),
    },
    STALLED_SCAN_TTL_SECONDS
  );

  return true;
}

export async function claimStalledScanDelivery(scanId: string): Promise<{
  status: 'missing' | 'claimed' | 'already_processing' | 'terminal';
  record?: StalledScanRecord;
}> {
  const stalledScan = await getStalledScan(scanId);
  if (!stalledScan) {
    return { status: 'missing' };
  }

  if (
    stalledScan.notificationState === 'sent'
    || stalledScan.notificationState === 'failed_permanent'
  ) {
    return { status: 'terminal', record: stalledScan };
  }

  if (stalledScan.notificationState === 'sending' && hasActiveDeliveryClaim(stalledScan)) {
    return { status: 'already_processing', record: stalledScan };
  }

  const claimedRecord: StalledScanRecord = {
    ...stalledScan,
    notificationState: 'sending',
    deliveryClaimedAt: new Date().toISOString(),
  };
  await cache.set(getStalledScanCacheKey(scanId), claimedRecord, STALLED_SCAN_TTL_SECONDS);

  return { status: 'claimed', record: claimedRecord };
}

function hasActiveDeliveryClaim(record: StalledScanRecord): boolean {
  if (!record.deliveryClaimedAt) {
    return false;
  }

  const claimedAtMs = Date.parse(record.deliveryClaimedAt);
  if (Number.isNaN(claimedAtMs)) {
    return false;
  }

  return Date.now() - claimedAtMs < STALLED_SCAN_DELIVERY_CLAIM_TTL_MS;
}

export async function resetStalledScanDelivery(scanId: string): Promise<boolean> {
  const stalledScan = await getStalledScan(scanId);
  if (!stalledScan) {
    return false;
  }

  await cache.set(
    getStalledScanCacheKey(scanId),
    {
      ...stalledScan,
      notificationState: 'pending',
      deliveryClaimedAt: undefined,
    },
    STALLED_SCAN_TTL_SECONDS
  );

  return true;
}

export async function markStalledScanDeliveryFailed(
  scanId: string,
  failureReason: string
): Promise<boolean> {
  const stalledScan = await getStalledScan(scanId);
  if (!stalledScan) {
    return false;
  }

  await cache.set(
    getStalledScanCacheKey(scanId),
    {
      ...stalledScan,
      notificationState: 'failed_permanent',
      deliveryClaimedAt: undefined,
      failedAt: new Date().toISOString(),
      failureReason,
    },
    STALLED_SCAN_TTL_SECONDS
  );

  return true;
}
