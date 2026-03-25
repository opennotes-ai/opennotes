import { query, createAsync, useSearchParams } from "@solidjs/router";
import { For, Show, Suspense } from "solid-js";
import { listSimulations } from "~/lib/api-client.server";
import SimulationCard from "~/components/SimulationCard";
import Pagination from "~/components/Pagination";
import BlogFeed from "~/components/BlogFeed";
import FontToggle from "~/components/FontToggle";
import EmptyState from "~/components/ui/empty-state";
import { BarChart3, AlertTriangle } from "~/components/ui/icons";

const getSimulations = query(async (page: number) => {
  "use server";
  try {
    return await listSimulations(page, 20);
  } catch (error) {
    console.error("Failed to load simulations:", error);
    return null;
  }
}, "simulations");

export default function SimulationsPage() {
  const [searchParams] = useSearchParams();
  const page = () => Math.max(1, Number(searchParams.page) || 1);
  const data = createAsync(() => getSimulations(page()));

  return (
    <main class="mx-auto max-w-6xl px-4 py-8">
      <div class="grid grid-cols-1 gap-8 md:grid-cols-[2fr_1fr]">
        <div>
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-lg font-semibold">Posts</h2>
            <div class="flex items-center gap-2">
              <span class="text-xs text-muted-foreground">Font:</span>
              <FontToggle />
            </div>
          </div>
          <Suspense fallback={<p class="text-muted-foreground">Loading posts...</p>}>
            <BlogFeed />
          </Suspense>
        </div>
        <div class="md:sticky md:top-20 md:self-start">
          <h2 class="text-lg font-semibold mb-4">Simulations</h2>
          <Suspense fallback={<p class="text-muted-foreground">Loading simulations...</p>}>
            <Show
              when={data()}
              keyed
              fallback={
                <EmptyState
                  variant="error"
                  icon={<AlertTriangle class="size-6" />}
                  message="Couldn't reach the API"
                  description="The server may be temporarily unavailable."
                  actionLabel="Try again"
                  actionHref="/"
                />
              }
            >
              {(response) => (
                <>
                  <Show when={response.meta}>
                    {(meta) => (
                      <p class="mb-2 text-sm text-muted-foreground">
                        {meta().count} simulation{meta().count !== 1 ? "s" : ""}
                      </p>
                    )}
                  </Show>
                  <Show
                    when={response.data.length > 0}
                    fallback={
                      <EmptyState
                        icon={<BarChart3 class="size-6" />}
                        message="No simulations yet"
                        description="Simulations appear here once they're created and completed."
                      />
                    }
                  >
                    <div class="space-y-3">
                      <For each={response.data}>
                        {(sim) => <SimulationCard simulation={sim} />}
                      </For>
                    </div>
                  </Show>
                  <Show when={response.meta && (response.meta.pages ?? 0) > 1}>
                    <Pagination
                      currentPage={response.meta?.page ?? page()}
                      totalPages={response.meta?.pages ?? 1}
                    />
                  </Show>
                </>
              )}
            </Show>
          </Suspense>
        </div>
      </div>
    </main>
  );
}
