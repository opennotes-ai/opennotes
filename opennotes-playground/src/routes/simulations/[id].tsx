import { query, createAsync, useParams, useLocation, A } from "@solidjs/router";
import { Show, Switch, Match, Suspense, createSignal, createEffect, on, lazy } from "solid-js";
import { getRequestEvent } from "solid-js/web";
import {
  getSimulation,
  getSimulationAnalysis,
  getSimulationDetailedAnalysis,
} from "~/lib/api-client.server";
import { createClient } from "~/lib/supabase-server";
import { formatDate, getMetric, humanizeLabel } from "~/lib/format";
import { Badge, type BadgeVariant } from "~/components/ui/badge";
import { SectionSkeleton } from "~/components/ui/skeleton";
import InlineTOC from "~/components/InlineTOC";
import type { SectionId } from "~/components/sections";
import SimulationSidebar from "~/components/SimulationSidebar";
import IdBadge from "~/components/ui/id-badge";
import PaginationControls from "~/components/ui/pagination-controls";

const LazyAnalysisSummary = lazy(() => import("~/components/AnalysisSummary"));
const LazyMetricsDisplay = lazy(() => import("~/components/MetricsDisplay"));
const LazyAgentProfiles = lazy(() => import("~/components/AgentProfiles"));
const LazyNoteDetails = lazy(() => import("~/components/NoteDetails"));

const PAGE_SIZE_OPTIONS = [10, 25, 50] as const;

type AuthMeta = {
  isAuthenticated: boolean;
  totalAgents?: number;
  agentsTruncated?: boolean;
};

async function checkAuth(): Promise<boolean> {
  try {
    const event = getRequestEvent();
    if (!event) return false;
    const supabase = createClient(event.request, event.response.headers);
    const { data: { user } } = await supabase.auth.getUser();
    return !!user;
  } catch {
    return false;
  }
}

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
    const isAuthenticated = await checkAuth();
    const data = await getSimulationAnalysis(id);

    const behaviors = data.data.attributes.agent_behaviors ?? [];
    const totalAgents = behaviors.length;
    const agentsTruncated = !isAuthenticated && totalAgents > 20;
    const visibleBehaviors = agentsTruncated
      ? behaviors.slice(0, 20)
      : behaviors;

    return {
      ...data,
      data: {
        ...data.data,
        attributes: {
          ...data.data.attributes,
          agent_behaviors: visibleBehaviors,
        },
      },
      _authMeta: { isAuthenticated, totalAgents, agentsTruncated } as AuthMeta,
    };
  } catch (error) {
    console.error("Failed to fetch analysis:", error);
    return null;
  }
}, "analysis");

const fetchDetailedAnalysis = query(async (
  id: string,
  page: number,
  pageSize: number,
  sortBy: "count" | "has_score",
  filterClassification: string[],
  filterStatus: string[],
) => {
  "use server";
  try {
    const isAuthenticated = await checkAuth();
    const effectivePage = isAuthenticated ? page : 1;
    const data = await getSimulationDetailedAnalysis(
      id, effectivePage, pageSize, sortBy, filterClassification, filterStatus,
    );
    const totalCount = data.meta?.count ?? 0;

    return {
      ...data,
      _authMeta: { isAuthenticated } as AuthMeta,
      _totalPages: Math.max(1, Math.ceil(totalCount / pageSize)),
    };
  } catch (error) {
    console.error("Failed to fetch detailed analysis:", error);
    return null;
  }
}, "detailed-analysis");

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

function AuthGateCTA(props: { shown: number; total: number; label: string }) {
  const location = useLocation();
  const returnTo = () => encodeURIComponent(location.pathname);

  return (
    <div class="mt-4 rounded-lg border border-primary/20 bg-primary/5 p-4 text-center">
      <p class="text-sm text-muted-foreground">
        Showing {props.shown} of {props.total} {props.label}.
      </p>
      <p class="mt-1 text-sm">
        <A href={`/login?returnTo=${returnTo()}`} class="font-medium text-primary hover:underline">
          Sign in
        </A>
        <span class="text-muted-foreground"> or </span>
        <A href={`/register?returnTo=${returnTo()}`} class="font-medium text-primary hover:underline">
          sign up
        </A>
        <span class="text-muted-foreground"> to see all {props.label}.</span>
      </p>
    </div>
  );
}

export default function SimulationDetailPage() {
  const params = useParams();
  const simulation = createAsync(() => fetchSimulation(params.id!));
  const analysis = createAsync(() => fetchAnalysis(params.id!));
  const [pageSize, setPageSize] = createSignal(10);
  const [notesPage, setNotesPage] = createSignal(1);
  const [sortBy, setSortBy] = createSignal("count");
  const [filterClassification, setFilterClassification] = createSignal<string[]>([]);
  const [filterStatus, setFilterStatus] = createSignal<string[]>([]);
  createEffect(on(() => params.id, () => setNotesPage(1)));
  createEffect(on(() => pageSize(), () => setNotesPage(1), { defer: true }));
  createEffect(on(() => sortBy(), () => setNotesPage(1), { defer: true }));
  createEffect(on(() => [filterClassification(), filterStatus()], () => setNotesPage(1), { defer: true }));
  const [loadedSections, setLoadedSections] = createSignal<Set<SectionId>>(new Set(["metadata"]));

  function handleSectionClick(id: SectionId) {
    setLoadedSections((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
    setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    }, 100);
  }

  const serverSortBy = () => (sortBy() === "has_score" ? "has_score" : "count") as "count" | "has_score";
  const detailed = createAsync(() => fetchDetailedAnalysis(
    params.id!, notesPage(), pageSize(), serverSortBy(), filterClassification(), filterStatus(),
  ));

  const simError = () => {
    const r = simulation();
    return isError(r) ? r._error : null;
  };

  const simData = () => {
    const r = simulation();
    return r && !isError(r) ? r : null;
  };

  return (
    <div class="mx-auto max-w-[1100px] px-4 py-8">
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
                <div class="flex gap-8">
                  <aside class="hidden w-48 shrink-0 lg:block">
                    <SimulationSidebar />
                  </aside>
                  <main class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <h1 class="text-2xl font-bold tracking-tight">
                      Simulation <IdBadge idValue={simResponse.data.id} variant="muted" />
                    </h1>
                    <Badge variant={STATUS_VARIANT[attrs.status] ?? "muted"}>
                      {humanizeLabel(attrs.status)}
                    </Badge>
                  </div>

                  <section id="metadata" class="mt-6 rounded-lg border border-border bg-card p-5">
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
                    </div>
                    <Show when={attrs.error_message}>
                      <div class="mt-3 rounded-md bg-red-100 px-3 py-2 text-sm text-red-800 dark:bg-red-900/30 dark:text-red-300">
                        Error: {attrs.error_message}
                      </div>
                    </Show>
                  </section>

                  <details class="mt-4 rounded-lg border border-border p-3">
                    <summary class="cursor-pointer text-sm font-medium">Simulation Mechanics</summary>
                    <div class="mt-3 grid grid-cols-2 gap-2 text-sm text-muted-foreground">
                      <div>Turns: <strong class="text-foreground">{attrs.cumulative_turns}</strong></div>
                      <div>Restarts: <strong class="text-foreground">{attrs.restart_count}</strong></div>
                      <div>
                        Orchestrator: <IdBadge idValue={attrs.orchestrator_id} variant="muted" />
                      </div>
                      <div>
                        Community Server: <IdBadge idValue={attrs.community_server_id} variant="muted" />
                      </div>
                    </div>
                  </details>

                  <InlineTOC loadedSections={loadedSections()} onSectionClick={handleSectionClick} />

                  <Suspense fallback={<p class="mt-6 text-muted-foreground">Loading analysis...</p>}>
                    <Show
                      when={analysis()}
                      keyed
                      fallback={<p class="mt-6 italic text-muted-foreground">Analysis unavailable.</p>}
                    >
                      {(analysisResponse) => {
                        const a = analysisResponse.data.attributes;
                        const meta = analysisResponse._authMeta;
                        return (
                          <div class="mt-8 space-y-8 divide-y divide-border [&>*]:pt-8 first:[&>*]:pt-0">
                            <Show when={loadedSections().has("note-quality") || loadedSections().has("rating-distribution")}>
                              <Suspense fallback={<SectionSkeleton />}>
                                <LazyAnalysisSummary
                                  noteQuality={a.note_quality}
                                  ratingDistribution={a.rating_distribution}
                                  pageSize={pageSize()}
                                />
                              </Suspense>
                            </Show>
                            <Show when={loadedSections().has("consensus-metrics") || loadedSections().has("scoring-coverage")}>
                              <Suspense fallback={<SectionSkeleton />}>
                                <LazyMetricsDisplay
                                  consensus={a.consensus_metrics}
                                  scoring={a.scoring_coverage}
                                />
                              </Suspense>
                            </Show>
                            <Show when={loadedSections().has("agent-behaviors")}>
                              <Suspense fallback={<SectionSkeleton />}>
                                <div>
                                  <LazyAgentProfiles agents={a.agent_behaviors} pageSize={pageSize()} />
                                  <Show when={meta?.agentsTruncated && meta.totalAgents}>
                                    <AuthGateCTA
                                      shown={20}
                                      total={meta!.totalAgents!}
                                      label="agents"
                                    />
                                  </Show>
                                </div>
                              </Suspense>
                            </Show>
                          </div>
                        );
                      }}
                    </Show>
                  </Suspense>

                  <Show when={loadedSections().has("per-note-breakdown")}>
                    <Suspense fallback={<SectionSkeleton />}>
                      <Show
                        when={detailed()}
                        keyed
                        fallback={<p class="mt-6 italic text-muted-foreground">Loading detailed analysis...</p>}
                      >
                        {(detailedResponse) => {
                          const authMeta = detailedResponse._authMeta;
                          const totalNotes = detailedResponse.meta?.count ?? 0;
                          const notesTruncated = !authMeta?.isAuthenticated && totalNotes > pageSize();
                          const totalPages = detailedResponse._totalPages ?? 1;
                          return (
                            <div class="mt-8 border-t border-border pt-8">
                              <Show when={detailedResponse.meta}>
                                {(meta) => (
                                  <p class="mb-2 text-sm text-muted-foreground">
                                    {notesTruncated
                                      ? `Showing ${pageSize()} of ${meta().count}`
                                      : meta().count}
                                    {" "}note{meta().count !== 1 ? "s" : ""} in detailed analysis
                                  </p>
                                )}
                              </Show>
                              <LazyNoteDetails
                                notes={detailedResponse.data}
                                currentTier={analysis()?.data?.attributes?.scoring_coverage?.current_tier ?? ""}
                                sortBy={sortBy() as "count" | "disagreement" | "has_score"}
                                onSortChange={setSortBy}
                                filterClassification={filterClassification()}
                                filterStatus={filterStatus()}
                                onFilterChange={(v) => {
                                  setFilterClassification(v.classification);
                                  setFilterStatus(v.status);
                                }}
                              />
                              <Show when={authMeta?.isAuthenticated && totalPages > 1}>
                                <PaginationControls
                                  currentPage={notesPage()}
                                  totalPages={totalPages}
                                  onPageChange={setNotesPage}
                                  label="Notes pagination"
                                  pageSize={pageSize()}
                                  pageSizeOptions={[...PAGE_SIZE_OPTIONS]}
                                  onPageSizeChange={setPageSize}
                                />
                              </Show>
                              <Show when={notesTruncated}>
                                <AuthGateCTA
                                  shown={pageSize()}
                                  total={totalNotes}
                                  label="notes"
                                />
                              </Show>
                            </div>
                          );
                        }}
                      </Show>
                    </Suspense>
                  </Show>
                  </main>
                </div>
              );
            }}
          </Match>
        </Switch>
      </Suspense>
    </div>
  );
}

function NotFound() {
  return (
    <div class="mt-16 text-center">
      <h1 class="text-4xl font-bold">404</h1>
      <p class="mt-2 text-muted-foreground">Simulation not found.</p>
      <a href="/" class="mt-4 inline-block text-primary hover:underline">
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
      <a href="/" class="mt-4 inline-block text-primary hover:underline">
        Back to simulations
      </a>
    </div>
  );
}
