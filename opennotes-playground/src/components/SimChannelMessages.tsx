import { Show, For, createSignal, createEffect } from "solid-js";
import { createAsync } from "@solidjs/router";
import { getAgentAvatar } from "~/lib/agent-avatar";
import { cn } from "~/lib/cn";
import { Skeleton } from "~/components/ui/skeleton";
import { Button } from "~/components/ui/button";
import { fetchChannelMessages } from "~/routes/simulations/[id]";
import type { components } from "~/lib/generated-types";

type SimChannelMessageResource =
  components["schemas"]["SimChannelMessageResource"];

export function SimChannelMessages(props: { simulationId: string }) {
  const [messages, setMessages] = createSignal<SimChannelMessageResource[]>([]);
  const [hasMore, setHasMore] = createSignal(false);
  const [loading, setLoading] = createSignal(false);
  let containerRef: HTMLDivElement | undefined;

  const initial = createAsync(() => fetchChannelMessages(props.simulationId));

  createEffect(() => {
    const data = initial();
    if (data) {
      setMessages(data.data);
      setHasMore(data.meta.has_more);
      requestAnimationFrame(() => {
        if (containerRef) containerRef.scrollTop = containerRef.scrollHeight;
      });
    }
  });

  async function loadMore() {
    const msgs = messages();
    if (msgs.length === 0 || loading()) return;
    setLoading(true);
    const oldestId = msgs[0].id;
    const oldScrollHeight = containerRef?.scrollHeight ?? 0;

    try {
      const result = await fetchChannelMessages(props.simulationId, oldestId);
      if (result) {
        setMessages([...result.data, ...msgs]);
        setHasMore(result.meta.has_more);
        requestAnimationFrame(() => {
          if (containerRef) {
            containerRef.scrollTop = containerRef.scrollHeight - oldScrollHeight;
          }
        });
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      ref={containerRef}
      class="h-[400px] overflow-y-auto rounded-lg border border-border bg-card lg:h-[500px]"
      role="log"
      aria-label="SIM channel messages"
    >
      <Show when={!initial()}>
        <div class="space-y-4 p-4">
          <For each={Array(5)}>
            {() => (
              <div class="flex gap-3">
                <Skeleton class="size-8 shrink-0 rounded-full" />
                <div class="space-y-1.5">
                  <Skeleton class="h-3.5 w-24" />
                  <Skeleton class="h-4 w-64" />
                </div>
              </div>
            )}
          </For>
        </div>
      </Show>

      <Show when={initial() && messages().length === 0}>
        <div class="flex h-full items-center justify-center">
          <p class="text-sm italic text-muted-foreground">No messages yet</p>
        </div>
      </Show>

      <Show when={messages().length > 0}>
        <div class="p-4">
          <Show when={hasMore()}>
            <div class="mb-4 flex justify-center">
              <Button
                variant="outline"
                size="sm"
                onClick={loadMore}
                disabled={loading()}
              >
                {loading() ? "Loading..." : "Load older messages"}
              </Button>
            </div>
          </Show>

          <div class="space-y-3">
            <For each={messages()}>
              {(msg) => {
                const avatar = getAgentAvatar(msg.attributes.agent_profile_id);
                const time = msg.attributes.created_at
                  ? new Date(msg.attributes.created_at).toLocaleTimeString(
                      [],
                      { hour: "2-digit", minute: "2-digit" },
                    )
                  : "";
                return (
                  <div class="flex gap-3">
                    <div
                      class={cn(
                        "flex size-8 shrink-0 items-center justify-center rounded-full text-base",
                        avatar.bgColor,
                      )}
                    >
                      {avatar.emoji}
                    </div>
                    <div class="min-w-0">
                      <div class="flex items-baseline gap-2">
                        <span class="text-sm font-semibold">
                          {msg.attributes.agent_name}
                        </span>
                        <span class="text-xs text-muted-foreground">
                          {time}
                        </span>
                      </div>
                      <p class="text-sm text-foreground">
                        {msg.attributes.message_text}
                      </p>
                    </div>
                  </div>
                );
              }}
            </For>
          </div>
        </div>
      </Show>
    </div>
  );
}
