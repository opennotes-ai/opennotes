import { query, createAsync, useSearchParams } from "@solidjs/router";
import { For, Show, Suspense } from "solid-js";
import { listSimulations } from "~/lib/api-client.server";
import SimulationCard from "~/components/SimulationCard";
import Pagination from "~/components/Pagination";
import BlogFeed from "~/components/BlogFeed";

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
      <h1 class="text-2xl font-bold tracking-tight">OpenNotes</h1>
      <div class="mt-6 grid grid-cols-1 gap-8 md:grid-cols-[2fr_1fr]">
        <div class="blog-serif:font-serif">
          <h2 class="text-lg font-semibold mb-4">Blog</h2>
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
                <div class="rounded-lg bg-red-100 p-6 text-center dark:bg-red-900/30">
                  <p class="font-medium text-red-800 dark:text-red-300">
                    Failed to load simulations. The API may be unreachable.
                  </p>
                  <a href="/" class="mt-2 inline-block text-primary hover:underline">Try again</a>
                </div>
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
                    fallback={<p class="text-muted-foreground">No simulations found.</p>}
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
