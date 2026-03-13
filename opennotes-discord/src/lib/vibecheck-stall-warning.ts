export interface StallWarningController {
  onStallWarning(scanId: string): Promise<void>;
  shouldSuppressUpdates(): Promise<boolean>;
}

export function createStallWarningController(
  handleWarning: (scanId: string) => Promise<void>
): StallWarningController {
  let stallActive = false;
  let pendingWarning: Promise<void> | null = null;

  return {
    async onStallWarning(scanId: string): Promise<void> {
      if (stallActive) {
        return;
      }

      if (!pendingWarning) {
        pendingWarning = (async (): Promise<void> => {
          try {
            await handleWarning(scanId);
            stallActive = true;
          } finally {
            pendingWarning = null;
          }
        })();
      }

      return pendingWarning;
    },

    async shouldSuppressUpdates(): Promise<boolean> {
      if (pendingWarning) {
        try {
          await pendingWarning;
        } catch {
          return false;
        }
      }

      return stallActive;
    },
  };
}
