import { query, createAsync, useSearchParams } from "@solidjs/router";
import { For, Show, Suspense } from "solid-js";
import { listSimulations } from "~/lib/api-client.server";
import SimulationCard from "~/components/SimulationCard";
import Pagination from "~/components/Pagination";

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
    <main style={{ "max-width": "800px", margin: "0 auto", padding: "2rem 1rem" }}>
      <h1>Simulations</h1>
      <Suspense fallback={<p>Loading simulations...</p>}>
        <Show
          when={data()}
          keyed
          fallback={
            <div style={{ "text-align": "center", "margin-top": "2rem", padding: "1.5rem", "background-color": "#f8d7da", "border-radius": "6px" }}>
              <p style={{ color: "#721c24", "font-weight": "500", margin: "0 0 0.5rem" }}>
                Failed to load simulations. The API may be unreachable.
              </p>
              <a href="/simulations" style={{ color: "#1976d2" }}>Try again</a>
            </div>
          }
        >
          {(response) => (
            <>
              <Show when={response.meta}>
                {(meta) => (
                  <p style={{ color: "#666" }}>
                    {meta().count} simulation{meta().count !== 1 ? "s" : ""} found
                  </p>
                )}
              </Show>
              <Show
                when={response.data.length > 0}
                fallback={<p>No simulations found.</p>}
              >
                <For each={response.data}>
                  {(sim) => <SimulationCard simulation={sim} />}
                </For>
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
    </main>
  );
}
