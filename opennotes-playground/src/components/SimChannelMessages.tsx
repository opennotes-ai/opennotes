import { Show, For, createSignal, createEffect } from "solid-js";
import { createAsync } from "@solidjs/router";
import { getAgentAvatar } from "~/lib/agent-avatar";
import { cn } from "@opennotes/ui/utils";
import { Skeleton } from "@opennotes/ui/components/ui/skeleton";
import { Button } from "@opennotes/ui/components/ui/button";
import { fetchChannelMessages } from "~/routes/simulations/[id]";
import type { components } from "~/lib/generated-types";
import EmptyState from "@opennotes/ui/components/ui/empty-state";
import { MessageCircle, AlertTriangle } from "@opennotes/ui/components/ui/icons";

type SimChannelMessageResource =
  components["schemas"]["SimChannelMessageResource"];

export function SimChannelMessages(props: { simulationId: string }) {
  const [messages, setMessages] = createSignal<SimChannelMessageResource[]>([]);
  const [hasMore, setHasMore] = createSignal(false);
  const [loading, setLoading] = createSignal(false);
  const [loadMoreError, setLoadMoreError] = createSignal(false);
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
    setLoadMoreError(false);
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
      } else {
        setLoadMoreError(true);
      }
    } catch {
      setLoadMoreError(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      ref={containerRef}
      class="h-[400px] overflow-y-auto rounded-xl border border-dashed border-border/50 bg-muted/20 lg:h-[500px]"
      role="log"
      aria-label="Chat channel messages"
    >
      <Show when={initial() === undefined}>
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

      <Show when={initial() === null}>
        <div class="flex h-full items-center justify-center">
          <EmptyState
            variant="error"
            icon={<AlertTriangle class="size-6" />}
            message="Couldn't load messages"
            description="The chat history may be temporarily unavailable."
          />
        </div>
      </Show>

      <Show when={initial() && messages().length === 0}>
        <div class="flex h-full items-center justify-center">
          <EmptyState
            icon={<MessageCircle class="size-6" />}
            message="No messages yet"
            description="Chat messages appear here once agents start discussing in the channel."
          />
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

          <Show when={loadMoreError()}>
            <p class="text-center text-xs text-destructive">Failed to load older messages</p>
          </Show>

          <div class="space-y-3">
            <For each={messages()}>
              {(msg) => {
                const avatar = getAgentAvatar(msg.attributes.agent_profile_id);
                const time = (() => {
                  if (!msg.attributes.created_at) return "";
                  const d = new Date(msg.attributes.created_at);
                  const now = new Date();
                  const isToday = d.getFullYear() === now.getFullYear()
                    && d.getMonth() === now.getMonth()
                    && d.getDate() === now.getDate();
                  const t = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
                  if (isToday) return t;
                  const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
                  return `${date}, ${t}`;
                })();
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
