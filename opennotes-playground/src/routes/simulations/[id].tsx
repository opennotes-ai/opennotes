import { query, createAsync, useParams } from "@solidjs/router";
import { Show, Switch, Match, Suspense } from "solid-js";
import {
  getSimulation,
  getSimulationAnalysis,
  getSimulationDetailedAnalysis,
} from "~/lib/api-client.server";
import { formatDate, humanizeLabel, truncateId } from "~/lib/format";
import { Badge, type BadgeVariant } from "~/components/ui/badge";
import AnalysisSummary from "~/components/AnalysisSummary";
import AgentProfiles from "~/components/AgentProfiles";
import MetricsDisplay from "~/components/MetricsDisplay";
import NoteDetails from "~/components/NoteDetails";

type SimulationError = { _error: "not_found" | "server_error" };

const fetchSimulation = query(async (id: string) => {
  "use server";
  try {
    return await getSimulation(id);
  } catch (error: unknown) {
    console.error("Failed to fetch simulation:", error);
    if (error instanceof Error && "statusCode" in error && (error as Error & { statusCode: number }).statusCode === 404) {
      return { _error: "not_found" as const };
    }
    return { _error: "server_error" as const };
  }
}, "simulation");

const fetchAnalysis = query(async (id: string) => {
  "use server";
  try {
    return await getSimulationAnalysis(id);
  } catch (error) {
    console.error("Failed to fetch analysis:", error);
    return null;
  }
}, "analysis");

const fetchDetailedAnalysis = query(async (id: string) => {
  "use server";
  try {
    return await getSimulationDetailedAnalysis(id, 1, 50);
  } catch (error) {
    console.error("Failed to fetch detailed analysis:", error);
    return null;
  }
}, "detailed-analysis");

function getMetric(
  metrics: Record<string, unknown> | null | undefined,
  key: string,
): string {
  if (!metrics || !(key in metrics)) return "N/A";
  return String(metrics[key]);
}

function isError(result: unknown): result is SimulationError {
  return result != null && typeof result === "object" && "_error" in result;
}

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  completed: "success",
  running: "warning",
  pending: "muted",
  failed: "danger",
  paused: "info",
};

export default function SimulationDetailPage() {
  const params = useParams();
  const simulation = createAsync(() => fetchSimulation(params.id!));
  const analysis = createAsync(() => fetchAnalysis(params.id!));
  const detailed = createAsync(() => fetchDetailedAnalysis(params.id!));

  const simError = () => {
    const r = simulation();
    return isError(r) ? r._error : null;
  };

  const simData = () => {
    const r = simulation();
    return r && !isError(r) ? r : null;
  };

  return (
    <main class="mx-auto max-w-[960px] px-4 py-8">
      <Suspense fallback={<p class="text-muted-foreground">Loading simulation...</p>}>
        <Switch>
          <Match when={simError() === "not_found"}>
            <NotFound />
          </Match>
          <Match when={simError() === "server_error"}>
            <ServerError />
          </Match>
          <Match when={simData()} keyed>
            {(simResponse) => {
              const attrs = simResponse.data.attributes;
              return (
                <>
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <h1 class="text-2xl font-bold tracking-tight">
                      Simulation {truncateId(simResponse.data.id)}
                    </h1>
                    <Badge variant={STATUS_VARIANT[attrs.status] ?? "muted"}>
                      {humanizeLabel(attrs.status)}
                    </Badge>
                  </div>

                  <section class="mt-6 rounded-lg border border-border bg-card p-5">
                    <h2 class="mb-3 text-lg font-semibold">Metadata</h2>
                    <div class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3 md:grid-cols-4">
                      <div>
                        <span class="text-muted-foreground">Status</span>
                        <div class="font-medium">{humanizeLabel(attrs.status)}</div>
                      </div>
                      <div>
                        <span class="text-muted-foreground">Created</span>
                        <div class="font-medium">{formatDate(attrs.created_at)}</div>
                      </div>
                      <Show when={attrs.started_at}>
                        <div>
                          <span class="text-muted-foreground">Started</span>
                          <div class="font-medium">{formatDate(attrs.started_at)}</div>
                        </div>
                      </Show>
                      <Show when={attrs.completed_at}>
                        <div>
                          <span class="text-muted-foreground">Completed</span>
                          <div class="font-medium">{formatDate(attrs.completed_at)}</div>
                        </div>
                      </Show>
                      <div>
                        <span class="text-muted-foreground">Agents</span>
                        <div class="font-medium">{getMetric(attrs.metrics, "agent_count")}</div>
                      </div>
                      <div>
                        <span class="text-muted-foreground">Notes</span>
                        <div class="font-medium">{getMetric(attrs.metrics, "note_count")}</div>
                      </div>
                      <div>
                        <span class="text-muted-foreground">Turns</span>
                        <div class="font-medium">{attrs.cumulative_turns}</div>
                      </div>
                      <div>
                        <span class="text-muted-foreground">Restarts</span>
                        <div class="font-medium">{attrs.restart_count}</div>
                      </div>
                    </div>
                    <Show when={attrs.error_message}>
                      <div class="mt-3 rounded-md bg-red-100 px-3 py-2 text-sm text-red-800 dark:bg-red-900/30 dark:text-red-300">
                        Error: {attrs.error_message}
                      </div>
                    </Show>
                    <div class="mt-3 text-xs text-muted-foreground">
                      Orchestrator: {truncateId(attrs.orchestrator_id)} | Community Server: {truncateId(attrs.community_server_id)}
                    </div>
                  </section>

                  <Suspense fallback={<p class="mt-6 text-muted-foreground">Loading analysis...</p>}>
                    <Show
                      when={analysis()}
                      keyed
                      fallback={<p class="mt-6 italic text-muted-foreground">Analysis unavailable.</p>}
                    >
                      {(analysisResponse) => {
                        const a = analysisResponse.data.attributes;
                        return (
                          <div class="mt-8 space-y-8">
                            <AnalysisSummary
                              noteQuality={a.note_quality}
                              ratingDistribution={a.rating_distribution}
                            />
                            <MetricsDisplay
                              consensus={a.consensus_metrics}
                              scoring={a.scoring_coverage}
                            />
                            <AgentProfiles agents={a.agent_behaviors} />
                          </div>
                        );
                      }}
                    </Show>
                  </Suspense>

                  <Suspense fallback={<p class="mt-6 text-muted-foreground">Loading detailed analysis...</p>}>
                    <Show
                      when={detailed()}
                      keyed
                      fallback={<p class="mt-6 italic text-muted-foreground">Detailed analysis unavailable.</p>}
                    >
                      {(detailedResponse) => (
                        <div class="mt-8">
                          <Show when={detailedResponse.meta}>
                            {(meta) => (
                              <p class="mb-2 text-sm text-muted-foreground">
                                {meta().count} note{meta().count !== 1 ? "s" : ""} in detailed analysis
                              </p>
                            )}
                          </Show>
                          <NoteDetails notes={detailedResponse.data} />
                        </div>
                      )}
                    </Show>
                  </Suspense>
                </>
              );
            }}
          </Match>
        </Switch>
      </Suspense>
    </main>
  );
}

function NotFound() {
  return (
    <div class="mt-16 text-center">
      <h1 class="text-4xl font-bold">404</h1>
      <p class="mt-2 text-muted-foreground">Simulation not found.</p>
      <a href="/simulations" class="mt-4 inline-block text-primary hover:underline">
        Back to simulations
      </a>
    </div>
  );
}

function ServerError() {
  return (
    <div class="mt-16 text-center">
      <h1 class="text-2xl font-bold text-red-700 dark:text-red-400">Server Error</h1>
      <p class="mt-2 text-muted-foreground">
        Something went wrong while loading this simulation. The API may be unreachable.
      </p>
      <a href="/simulations" class="mt-4 inline-block text-primary hover:underline">
        Back to simulations
      </a>
    </div>
  );
}
