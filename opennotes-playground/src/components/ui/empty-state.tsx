import type { JSX, ComponentProps } from "solid-js";
import { Show, splitProps } from "solid-js";
import { A } from "@solidjs/router";
import { cn } from "@opennotes/ui/utils";

interface EmptyStateProps extends ComponentProps<"div"> {
  icon?: JSX.Element;
  message: string;
  description?: string;
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
  variant?: "default" | "error";
}

export default function EmptyState(props: EmptyStateProps) {
  const [local, rest] = splitProps(props, [
    "icon", "message", "description", "actionLabel", "actionHref", "onAction", "variant", "class",
  ]);
  const isError = () => local.variant === "error";
  return (
    <div class={cn(
      "rounded-lg px-6 py-8 text-center",
      isError() ? "bg-destructive/10" : "bg-muted/30",
      local.class,
    )} {...rest}>
      <Show when={local.icon}>
        <div class="mx-auto mb-3 text-muted-foreground">{local.icon}</div>
      </Show>
      <p class="font-medium">{local.message}</p>
      <Show when={local.description}>
        <p class="mt-1 text-sm text-muted-foreground">{local.description}</p>
      </Show>
      <Show when={local.actionLabel && (local.actionHref || local.onAction)}>
        <div class="mt-3">
          <Show
            when={local.actionHref}
            fallback={
              <button
                onClick={local.onAction}
                class="text-sm font-medium text-primary hover:underline"
              >
                {local.actionLabel}
              </button>
            }
          >
            <A href={local.actionHref!} class="text-sm font-medium text-primary hover:underline">
              {local.actionLabel}
            </A>
          </Show>
        </div>
      </Show>
    </div>
  );
}
