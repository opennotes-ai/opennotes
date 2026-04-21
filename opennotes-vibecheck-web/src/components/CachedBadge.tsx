import { Show } from "solid-js";
import { Badge } from "@opennotes/ui/components/ui/badge";

export interface CachedBadgeProps {
  cached: boolean;
  cachedAt?: string | null;
}

function formatRelative(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return null;
  const deltaMs = Date.now() - ts;
  if (deltaMs < 0) return "just now";
  const minutes = Math.floor(deltaMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function CachedBadge(props: CachedBadgeProps) {
  return (
    <Show when={props.cached}>
      <Badge
        variant="muted"
        data-testid="cached-badge"
        class="gap-1 rounded-full"
        title="Served from the vibecheck cache"
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 16 16"
          width="12"
          height="12"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <circle cx="8" cy="8" r="6" />
          <path d="M8 5v3l2 1.5" />
        </svg>
        <span>cached</span>
        <Show when={formatRelative(props.cachedAt)}>
          {(rel) => (
            <span class="text-muted-foreground/80">&middot; {rel()}</span>
          )}
        </Show>
      </Badge>
    </Show>
  );
}
