import { query, createAsync, useParams, useLocation, A } from "@solidjs/router";
import { Title } from "@solidjs/meta";
import { Show, Switch, Match, Suspense, createSignal, createEffect, on, untrack } from "solid-js";
import EmptyState from "@opennotes/ui/components/ui/empty-state";
import { AlertCircle, Search } from "@opennotes/ui/components/ui/icons";
import {
  getSimulation,
  getSimulationAnalysis,
  getSimulationDetailedAnalysis,
  getSimulationTimeline,
  getSimulationChannelMessages,
} from "~/lib/api-client.server";
import {
  parseFragment,
  scrollToAndHighlight,
  findPageForItem,
} from "@opennotes/ui/utils";
import {
  formatDate,
  formatIdBadgeLabel,
  getMetric,
  humanizeLabel,
} from "~/lib/format";
import { Badge, type BadgeVariant } from "@opennotes/ui/components/ui/badge";
import { SectionSkeleton } from "@opennotes/ui/components/ui/skeleton";
import SimulationSidebar, { MobileSidebarToggle } from "~/components/SimulationSidebar";
import IdBadge from "@opennotes/ui/components/ui/id-badge";
import PaginationControls from "@opennotes/ui/components/ui/pagination-controls";
import AgentsSection from "~/components/AgentsSection";
import NotesRatingsSection from "~/components/NotesRatingsSection";
import ScoringAnalysisSection from "~/components/ScoringAnalysisSection";
import NoteDetails from "~/components/NoteDetails";
import { SimChannelMessages } from "~/components/SimChannelMessages";
import SectionHeader from "@opennotes/ui/components/ui/section-header";

const PAGE_SIZE_OPTIONS = [10, 25, 50] as const;

type AuthMeta = {
  isAuthenticated: boolean;
  totalAgents?: number;
  agentsTruncated?: boolean;
};

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
    const { getUser } = await import("~/lib/supabase-server");
    const user = await getUser();
    const isAuthenticated = !!user;
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
    const { getUser } = await import("~/lib/supabase-server");
    const user = await getUser();
    const isAuthenticated = !!user;
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

const fetchTimeline = query(async (id: string) => {
  "use server";
  try {
    return await getSimulationTimeline(id);
  } catch (error) {
    console.error("Failed to fetch timeline:", error);
    return null;
  }
}, "timeline");

const fetchChannelMessages = query(async (id: string, before?: string) => {
  "use server";
  try {
    return await getSimulationChannelMessages(id, 20, before);
  } catch (error) {
    console.error("Failed to fetch channel messages:", error);
    return null;
  }
}, "channel-messages");

export { fetchChannelMessages };

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
  const timeline = createAsync(() => fetchTimeline(params.id!));
  const [pageSize, setPageSize] = createSignal(10);
  const [notesPage, setNotesPage] = createSignal(1);
  const [sortBy, setSortBy] = createSignal("count");
  const [filterClassification, setFilterClassification] = createSignal<string[]>([]);
  const [filterStatus, setFilterStatus] = createSignal<string[]>([]);
  createEffect(on(() => params.id, () => setNotesPage(1)));
  createEffect(on(() => pageSize(), () => setNotesPage(1), { defer: true }));
  createEffect(on(() => sortBy(), () => setNotesPage(1), { defer: true }));
  createEffect(on(() => [filterClassification(), filterStatus()], () => setNotesPage(1), { defer: true }));

  const [anchorAgentPage, setAnchorAgentPage] = createSignal<number | undefined>(undefined);
  const initialHash = typeof window !== "undefined" ? window.location.hash : "";
  const [pendingAgentAnchor, setPendingAgentAnchor] = createSignal<boolean>(
    initialHash.startsWith("#agent-"),
  );
  const [pendingNoteAnchor, setPendingNoteAnchor] = createSignal<string | null>(
    initialHash.startsWith("#note-") || initialHash.startsWith("#request-") ? initialHash : null,
  );

  createEffect(() => {
    if (typeof window === "undefined") return;
    if (!pendingAgentAnchor()) return;
    const hash = window.location.hash;
    if (!hash || !hash.startsWith("#agent-")) return;
    const a = analysis();
    if (!a || !("data" in a)) return;
    const agents = a.data.attributes.agent_behaviors;
    const target = parseFragment(hash, agents.map(ag => ({ id: ag.agent_profile_id })), "agent");
    if (target) {
      setPendingAgentAnchor(false);
      const agentPage = findPageForItem(agents, target.id, pageSize(), (ag) => ag.agent_profile_id);
      setAnchorAgentPage(agentPage);
      scrollToAndHighlight(`agent-${target.id}`);
    }
  });

  const serverSortBy = () => (sortBy() === "has_score" ? "has_score" : "count") as "count" | "has_score";
  const detailed = createAsync(() => fetchDetailedAnalysis(
    params.id!, notesPage(), pageSize(), serverSortBy(), filterClassification(), filterStatus(),
  ));

  createEffect(() => {
    const anchor = pendingNoteAnchor();
    if (!anchor) return;

    const d = detailed();
    if (!d || !("data" in d)) return;

    const notes = d.data;
    const type = anchor.startsWith("#note-") ? "note" as const : "request" as const;

    const items: Array<{ id: string }> = type === "note"
      ? notes.map(n => ({ id: n.attributes.note_id }))
      : [...new Set(notes.map(n => n.attributes.request_id).filter(Boolean))].map(id => ({ id: id! }));

    const parsed = parseFragment(anchor, items, type);

    if (parsed) {
      setPendingNoteAnchor(null);
      scrollToAndHighlight(`${type}-${parsed.id}`);
      return;
    }

    if (!d._authMeta?.isAuthenticated) {
      setPendingNoteAnchor(null);
      return;
    }

    const totalPages = d._totalPages ?? 1;
    const currentPage = untrack(() => notesPage());
    if (currentPage < totalPages) {
      setNotesPage(currentPage + 1);
    } else {
      setPendingNoteAnchor(null);
    }
  });

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
                  <Title>Open Notes Playground - Simulation {formatIdBadgeLabel(simResponse.data.id, attrs.name)}</Title>
                  <SimulationSidebar />
                  <main class="min-w-0 flex-1">
                  <MobileSidebarToggle />
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <h1 class="text-2xl font-bold tracking-tight">
                      Simulation <IdBadge idValue={simResponse.data.id} name={attrs.name} variant="muted" />
                    </h1>
                    <Badge variant={STATUS_VARIANT[attrs.status] ?? "muted"}>
                      {humanizeLabel(attrs.status)}
                    </Badge>
                  </div>

                  <div id="metadata" class="mt-4 flex flex-wrap gap-x-6 gap-y-1 border-b border-border pb-4 text-sm text-muted-foreground">
                    <span><span class="font-medium text-foreground">{humanizeLabel(attrs.status)}</span></span>
                    <span>Created: <span class="font-medium text-foreground">{formatDate(attrs.created_at)}</span></span>
                    <Show when={attrs.started_at}>
                      <span>Started: <span class="font-medium text-foreground">{formatDate(attrs.started_at)}</span></span>
                    </Show>
                    <Show when={attrs.completed_at}>
                      <span>Completed: <span class="font-medium text-foreground">{formatDate(attrs.completed_at)}</span></span>
                    </Show>
                    <span>Agents: <span class="font-medium text-foreground">{getMetric(attrs.metrics, "agent_count")}</span></span>
                    <span>Notes: <span class="font-medium text-foreground">{getMetric(attrs.metrics, "note_count")}</span></span>
                    <Show when={attrs.error_message}>
                      <span class="basis-full text-sm text-red-700 dark:text-red-400">Error: {attrs.error_message}</span>
                    </Show>
                  </div>

                  <Suspense fallback={<p class="mt-6 text-muted-foreground">Loading analysis...</p>}>
                    <Show
                      when={analysis()}
                      keyed
                      fallback={
                        <div class="mt-6">
                          <EmptyState
                            icon={<AlertCircle class="size-6" />}
                            message="Analysis unavailable"
                            description="Analysis data for this simulation couldn't be loaded."
                          />
                        </div>
                      }
                    >
                      {(analysisResponse) => {
                        const a = analysisResponse.data.attributes;
                        const meta = analysisResponse._authMeta;
                        return (
                          <div class="mt-10 space-y-10">
                            <div>
                              <AgentsSection
                                agents={a.agent_behaviors}
                                ratingDistribution={a.rating_distribution}
                                pageSize={pageSize()}
                                anchorPage={anchorAgentPage()}
                              />
                              <Show when={meta?.agentsTruncated && meta.totalAgents}>
                                <AuthGateCTA
                                  shown={20}
                                  total={meta!.totalAgents!}
                                  label="agents"
                                />
                              </Show>
                            </div>

                            <NotesRatingsSection
                              noteQuality={a.note_quality}
                              ratingDistribution={a.rating_distribution}
                              buckets={timeline()?.data?.attributes?.buckets}
                              totalNotes={timeline()?.data?.attributes?.total_notes}
                              totalRatings={timeline()?.data?.attributes?.total_ratings}
                            />

                            <ScoringAnalysisSection
                              consensus={a.consensus_metrics}
                              scoring={a.scoring_coverage}
                            />
                          </div>
                        );
                      }}
                    </Show>
                  </Suspense>

                  <Suspense fallback={<SectionSkeleton />}>
                    <Show
                      when={detailed()}
                      keyed
                      fallback={
                        <div class="mt-6">
                          <EmptyState
                            icon={<AlertCircle class="size-6" />}
                            message="Detailed analysis unavailable"
                            description="Per-note breakdown data couldn't be loaded."
                          />
                        </div>
                      }
                    >
                      {(detailedResponse) => {
                        const authMeta = detailedResponse._authMeta;
                        const totalNotes = detailedResponse.meta?.count ?? 0;
                        const notesTruncated = !authMeta?.isAuthenticated && totalNotes > pageSize();
                        const totalPages = detailedResponse._totalPages ?? 1;
                        return (
                          <section id="note-details" class="mt-12">
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
                            <NoteDetails
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
                          </section>
                        );
                      }}
                    </Show>
                  </Suspense>

                  <section id="sim-channel" class="mt-12">
                    <SectionHeader title="The Conversation" subtitle="How agents discussed and debated in the community channel" />
                    <Suspense fallback={<SectionSkeleton />}>
                      <SimChannelMessages simulationId={params.id!} />
                    </Suspense>
                  </section>
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
    <div class="mt-16">
      <EmptyState
        icon={<Search class="size-6" />}
        message="Simulation not found"
        description="This simulation may have been removed, or the link might be outdated."
        actionLabel="Back to home"
        actionHref="/"
      />
    </div>
  );
}

function ServerError() {
  return (
    <div class="mt-16">
      <EmptyState
        variant="error"
        icon={<AlertCircle class="size-6" />}
        message="Something went wrong"
        description="We had trouble loading this simulation. The server may be temporarily unavailable."
        actionLabel="Back to home"
        actionHref="/"
      />
    </div>
  );
}
