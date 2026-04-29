import { type ChildProcess } from "node:child_process";
import { once } from "node:events";

export async function stopWebProcess(process: ChildProcess): Promise<void> {
  if (process.exitCode !== null || process.signalCode !== null) return;

  const exitPromise = once(process, "exit").then(() => undefined);
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const timeoutPromise = new Promise<boolean>((resolve) => {
    timeoutId = setTimeout(() => resolve(false), 5_000);
  });

  process.kill("SIGTERM");
  const exited = await Promise.race([
    exitPromise.then(() => true),
    timeoutPromise,
  ]).finally(() => {
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = undefined;
    }
  });

  if (!exited && process.exitCode === null && process.signalCode === null) {
    process.kill("SIGKILL");
    await exitPromise;
  }
}
