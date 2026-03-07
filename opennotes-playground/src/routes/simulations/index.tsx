import { query, createAsync, useSearchParams } from "@solidjs/router";
import { For, Show, Suspense } from "solid-js";
import { listSimulations } from "~/lib/api-client.server";
import SimulationCard from "~/components/SimulationCard";
import Pagination from "~/components/Pagination";

const getSimulations = query(async (page: number) => {
  "use server";
  try {
    return await listSimulations(page, 20);
  } catch {
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
        <Show when={data()} keyed>
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
