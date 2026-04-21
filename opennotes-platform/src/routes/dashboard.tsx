import {
  action,
  createAsync,
  query,
  revalidate,
  useAction,
  useSubmission,
} from "@solidjs/router";
import {
  createSignal,
  For,
  Match,
  Show,
  Switch,
  Suspense,
} from "solid-js";
import type { AdminAPIKey } from "~/lib/api-client.server";

const SCOPE_TEMPLATES: Record<string, string[]> = {
  "Discourse Plugin": [
    "requests:read",
    "requests:write",
    "notes:read",
    "notes:write",
    "ratings:write",
    "profiles:read",
    "community-servers:read",
    "moderation-actions:read",
  ],
  "Full Access": [
    "requests:read",
    "requests:write",
    "notes:read",
    "notes:write",
    "notes:delete",
    "ratings:write",
    "profiles:read",
    "community-servers:read",
    "moderation-actions:read",
  ],
  "Read Only": [
    "requests:read",
    "notes:read",
    "profiles:read",
    "community-servers:read",
    "moderation-actions:read",
  ],
};

const ALL_PUBLIC_SCOPES = [
  "requests:read",
  "requests:write",
  "notes:read",
  "notes:write",
  "notes:delete",
  "ratings:write",
  "profiles:read",
  "community-servers:read",
  "moderation-actions:read",
];

const getKeys = query(async () => {
  "use server";
  const { requireAuth } = await import("~/lib/auth-guard");
  await requireAuth();
  const { listAdminApiKeys } = await import("~/lib/api-client.server");
  try {
    return { data: await listAdminApiKeys(), _error: null };
  } catch (error: unknown) {
    console.error("Failed to list API keys:", error);
    return { data: null, _error: "server_error" as const };
  }
}, "keys");

const createKeyAction = action(async (formData: FormData) => {
  "use server";
  const { requireAuth } = await import("~/lib/auth-guard");
  const user = await requireAuth();
  const { createAdminApiKey } = await import("~/lib/api-client.server");
  const keyName = formData.get("keyName") as string;
  const scopes = formData.getAll("scopes") as string[];
  if (!keyName || scopes.length === 0) {
    return { _error: "validation" as const, key: null };
  }
  try {
    const result = await createAdminApiKey({
      user_email: user.email!,
      user_display_name: user.user_metadata?.full_name || user.email!,
      key_name: keyName,
      scopes,
    });
    await revalidate("keys");
    return { key: result, _error: null };
  } catch (error: unknown) {
    console.error("Failed to create API key:", error);
    return { _error: "server_error" as const, key: null };
  }
}, "createKey");

const revokeKeyAction = action(async (formData: FormData) => {
  "use server";
  const { requireAuth } = await import("~/lib/auth-guard");
  await requireAuth();
  const { revokeAdminApiKey } = await import("~/lib/api-client.server");
  const keyId = formData.get("keyId") as string;
  try {
    await revokeAdminApiKey(keyId);
    await revalidate("keys");
    return { _error: null };
  } catch (error: unknown) {
    console.error("Failed to revoke API key:", error);
    return { _error: "server_error" as const };
  }
}, "revokeKey");

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function scopesSummary(scopes: string[] | null): string {
  if (!scopes || scopes.length === 0) return "No scopes";
  if (scopes.length <= 2) return scopes.join(", ");
  return `${scopes.slice(0, 2).join(", ")} +${scopes.length - 2}`;
}

export default function DashboardPage() {
  const keysResult = createAsync(() => getKeys());
  const createSubmission = useSubmission(createKeyAction);
  const revokeSubmission = useSubmission(revokeKeyAction);
  const createKey = useAction(createKeyAction);
  const revokeKey = useAction(revokeKeyAction);

  const [showCreateForm, setShowCreateForm] = createSignal(false);
  const [selectedScopes, setSelectedScopes] = createSignal<Set<string>>(
    new Set(),
  );
  const [keyName, setKeyName] = createSignal("");
  const [revealedKey, setRevealedKey] = createSignal<AdminAPIKey | null>(null);
  const [revokeTarget, setRevokeTarget] = createSignal<AdminAPIKey | null>(
    null,
  );
  const [copied, setCopied] = createSignal(false);
  const [createError, setCreateError] = createSignal<string | null>(null);
  const [revokeError, setRevokeError] = createSignal<string | null>(null);

  function toggleScope(scope: string) {
    setSelectedScopes((prev) => {
      const next = new Set(prev);
      if (next.has(scope)) {
        next.delete(scope);
      } else {
        next.add(scope);
      }
      return next;
    });
  }

  function applyTemplate(templateName: string) {
    const scopes = SCOPE_TEMPLATES[templateName];
    if (scopes) {
      setSelectedScopes(new Set(scopes));
    }
  }

  function isTemplateActive(templateName: string): boolean {
    const templateScopes = SCOPE_TEMPLATES[templateName];
    if (!templateScopes) return false;
    const current = selectedScopes();
    if (current.size !== templateScopes.length) return false;
    return templateScopes.every((s) => current.has(s));
  }

  function resetForm() {
    setShowCreateForm(false);
    setSelectedScopes(new Set<string>());
    setKeyName("");
    setCreateError(null);
  }

  async function handleCreateSubmit(e: SubmitEvent) {
    e.preventDefault();
    setCreateError(null);
    const form = e.currentTarget as HTMLFormElement;
    const formData = new FormData(form);
    formData.set("keyName", keyName());
    for (const scope of selectedScopes()) {
      formData.append("scopes", scope);
    }
    const result = await createKey(formData);
    if (result._error === "validation") {
      setCreateError("Please provide a key name and select at least one scope.");
    } else if (result._error === "server_error") {
      setCreateError("Failed to create key. Please try again.");
    } else if (result.key) {
      setRevealedKey(result.key);
      resetForm();
    }
  }

  async function handleRevoke() {
    const target = revokeTarget();
    if (!target) return;
    setRevokeError(null);
    const formData = new FormData();
    formData.set("keyId", target.id);
    const result = await revokeKey(formData);
    if (result._error) {
      setRevokeError("Failed to revoke key. Please try again.");
    } else {
      setRevokeTarget(null);
    }
  }

  async function copyToClipboard(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      alert("Failed to copy. Please select and copy the key manually.");
    }
  }

  return (
    <main class="mx-auto max-w-4xl px-4 py-8">
      <div class="flex items-center justify-between">
        <h1 class="text-2xl font-bold tracking-tight">API Keys</h1>
        <Show when={!showCreateForm()}>
          <button
            onClick={() => setShowCreateForm(true)}
            class="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <svg
              class="h-4 w-4"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <path d="M12 5v14m-7-7h14" />
            </svg>
            Create Key
          </button>
        </Show>
      </div>

      <Show when={showCreateForm()}>
        <div class="mt-6 rounded-lg border border-border bg-card p-6">
          <h2 class="text-lg font-semibold">Create a new API key</h2>
          <form onSubmit={handleCreateSubmit} class="mt-4 space-y-5">
            <div>
              <label
                for="keyName"
                class="block text-sm font-medium text-foreground"
              >
                Key name
              </label>
              <input
                id="keyName"
                type="text"
                value={keyName()}
                onInput={(e) => setKeyName(e.currentTarget.value)}
                placeholder="e.g. Production Discourse"
                class="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
                required
              />
            </div>

            <div>
              <span class="block text-sm font-medium text-foreground">
                Templates
              </span>
              <div class="mt-2 flex flex-wrap gap-2">
                <For each={Object.keys(SCOPE_TEMPLATES)}>
                  {(name) => (
                    <button
                      type="button"
                      onClick={() => applyTemplate(name)}
                      class={`rounded-full border px-3 py-1 text-sm font-medium transition-colors ${
                        isTemplateActive(name)
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border bg-muted text-muted-foreground hover:bg-muted/80"
                      }`}
                    >
                      {name}
                    </button>
                  )}
                </For>
              </div>
            </div>

            <div>
              <span class="block text-sm font-medium text-foreground">
                Scopes
              </span>
              <div class="mt-2 flex flex-wrap gap-2">
                <For each={ALL_PUBLIC_SCOPES}>
                  {(scope) => (
                    <button
                      type="button"
                      onClick={() => toggleScope(scope)}
                      class={`rounded-md border px-2.5 py-1 text-xs font-medium transition-colors ${
                        selectedScopes().has(scope)
                          ? "border-primary/50 bg-primary/10 text-primary"
                          : "border-border bg-background text-muted-foreground hover:border-primary/30"
                      }`}
                    >
                      {scope}
                    </button>
                  )}
                </For>
              </div>
            </div>

            <Show when={createError()}>
              <p class="text-sm text-destructive">{createError()}</p>
            </Show>

            <div class="flex items-center gap-3">
              <button
                type="submit"
                disabled={
                  selectedScopes().size === 0 ||
                  !keyName() ||
                  createSubmission.pending
                }
                class="inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Show
                  when={!createSubmission.pending}
                  fallback="Creating..."
                >
                  Create Key
                </Show>
              </button>
              <button
                type="button"
                onClick={resetForm}
                class="text-sm text-muted-foreground hover:text-foreground"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      </Show>

      <Suspense
        fallback={
          <div class="mt-8 space-y-3">
            <div class="h-12 animate-pulse rounded-md bg-muted" />
            <div class="h-12 animate-pulse rounded-md bg-muted" />
            <div class="h-12 animate-pulse rounded-md bg-muted" />
          </div>
        }
      >
        <KeysTable
          keysResult={keysResult()}
          onRevoke={setRevokeTarget}
        />
      </Suspense>

      <Show when={revealedKey()}>
        {(key) => (
          <KeyRevealModal
            apiKey={key()}
            copied={copied()}
            onCopy={() => copyToClipboard(key().key)}
            onDismiss={() => {
              setRevealedKey(null);
              setCopied(false);
            }}
          />
        )}
      </Show>

      <Show when={revokeTarget()}>
        {(target) => (
          <RevokeConfirmDialog
            keyName={target().name}
            revokeError={revokeError()}
            pending={revokeSubmission.pending ?? false}
            onConfirm={handleRevoke}
            onCancel={() => {
              setRevokeTarget(null);
              setRevokeError(null);
            }}
          />
        )}
      </Show>
    </main>
  );
}

function KeysTable(props: {
  keysResult:
    | { data: AdminAPIKey[] | null; _error: "server_error" | null }
    | undefined;
  onRevoke: (key: AdminAPIKey) => void;
}) {
  return (
    <Switch>
      <Match when={props.keysResult?._error}>
        <div class="mt-8 rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-center">
          <p class="text-sm text-destructive">
            Failed to load API keys. The server may be unreachable.
          </p>
          <button
            onClick={() => revalidate("keys")}
            class="mt-3 text-sm font-medium text-primary hover:underline"
          >
            Retry
          </button>
        </div>
      </Match>
      <Match
        when={
          props.keysResult?.data && props.keysResult.data.length === 0
        }
      >
        <div class="mt-8 rounded-lg border border-border bg-card p-8 text-center">
          <div class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
            <svg
              class="h-6 w-6 text-muted-foreground"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
              viewBox="0 0 24 24"
            >
              <path d="M15.75 5.25a3 3 0 0 1 3 3m3 0a6 6 0 0 1-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1 1 21.75 8.25Z" />
            </svg>
          </div>
          <h3 class="text-base font-semibold">No API keys yet</h3>
          <p class="mt-1 text-sm text-muted-foreground">
            Create your first API key to start integrating with the
            Open Notes API.
          </p>
        </div>
      </Match>
      <Match when={props.keysResult?.data}>
        {(keys) => (
          <div class="mt-8">
            <div class="overflow-x-auto rounded-lg border border-border">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b border-border bg-muted/50">
                    <th class="px-4 py-3 text-left font-medium text-muted-foreground">
                      Name
                    </th>
                    <th class="hidden px-4 py-3 text-left font-medium text-muted-foreground sm:table-cell">
                      Scopes
                    </th>
                    <th class="hidden px-4 py-3 text-left font-medium text-muted-foreground md:table-cell">
                      Created
                    </th>
                    <th class="px-4 py-3 text-right font-medium text-muted-foreground">
                      <span class="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <For each={keys()}>
                    {(key) => (
                      <tr class="border-b border-border last:border-b-0">
                        <td class="px-4 py-3">
                          <div class="font-medium text-foreground">
                            {key.name}
                          </div>
                          <div class="mt-0.5 text-xs text-muted-foreground">
                            {key.key_prefix
                              ? `${key.key_prefix}...`
                              : key.user_email}
                          </div>
                        </td>
                        <td class="hidden px-4 py-3 text-muted-foreground sm:table-cell">
                          <span title={key.scopes?.join(", ") ?? ""}>
                            {scopesSummary(key.scopes)}
                          </span>
                        </td>
                        <td class="hidden px-4 py-3 text-muted-foreground md:table-cell">
                          {formatDate(key.created_at)}
                        </td>
                        <td class="px-4 py-3 text-right">
                          <button
                            onClick={() => props.onRevoke(key)}
                            class="text-sm text-destructive hover:text-destructive/80"
                          >
                            Revoke
                          </button>
                        </td>
                      </tr>
                    )}
                  </For>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Match>
    </Switch>
  );
}

function KeyRevealModal(props: {
  apiKey: AdminAPIKey;
  copied: boolean;
  onCopy: () => void;
  onDismiss: () => void;
}) {
  return (
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        class="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg animate-content-show"
        role="dialog"
        aria-labelledby="key-reveal-title"
        aria-modal="true"
      >
        <h3 id="key-reveal-title" class="text-lg font-semibold">
          API Key Created
        </h3>
        <p class="mt-2 text-sm text-muted-foreground">
          Copy this key now. You will not be able to see it again.
        </p>
        <div class="mt-4 rounded-md border border-border bg-muted p-3">
          <code class="block break-all text-sm text-foreground">
            {props.apiKey.key}
          </code>
        </div>
        <div class="mt-4 flex items-center gap-3">
          <button
            onClick={props.onCopy}
            class="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
          >
            <Show
              when={!props.copied}
              fallback={
                <>
                  <svg
                    class="h-4 w-4 text-primary"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                  >
                    <path d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                  Copied
                </>
              }
            >
              <svg
                class="h-4 w-4"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
              >
                <path d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9.75a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184" />
              </svg>
              Copy to Clipboard
            </Show>
          </button>
        </div>
        <div class="mt-4 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2">
          <p class="text-xs text-destructive">
            This is the only time this key will be shown. Store it
            securely.
          </p>
        </div>
        <div class="mt-5 flex justify-end">
          <button
            onClick={props.onDismiss}
            class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            I've saved my key
          </button>
        </div>
      </div>
    </div>
  );
}

function RevokeConfirmDialog(props: {
  keyName: string;
  revokeError: string | null;
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        class="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg animate-content-show"
        role="alertdialog"
        aria-labelledby="revoke-title"
        aria-describedby="revoke-desc"
        aria-modal="true"
      >
        <h3 id="revoke-title" class="text-lg font-semibold">
          Revoke API Key
        </h3>
        <p id="revoke-desc" class="mt-2 text-sm text-muted-foreground">
          Are you sure you want to revoke{" "}
          <span class="font-medium text-foreground">{props.keyName}</span>?
          Any integrations using this key will stop working immediately.
        </p>
        <Show when={props.revokeError}>
          <p class="mt-3 text-sm text-destructive">{props.revokeError}</p>
        </Show>
        <div class="mt-5 flex justify-end gap-3">
          <button
            onClick={props.onCancel}
            class="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted"
          >
            Cancel
          </button>
          <button
            onClick={props.onConfirm}
            disabled={props.pending}
            class="rounded-md bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground transition-colors hover:bg-destructive/90 disabled:opacity-50"
          >
            <Show when={!props.pending} fallback="Revoking...">
              Revoke Key
            </Show>
          </button>
        </div>
      </div>
    </div>
  );
}
