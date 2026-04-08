import { createAsync } from "@solidjs/router";
import { requireAuth } from "~/lib/auth-guard";

export default function DashboardPage() {
  const user = createAsync(() => requireAuth());

  return (
    <main class="mx-auto max-w-4xl px-4 py-8">
      <h1 class="text-2xl font-bold tracking-tight">Dashboard</h1>
      <p class="mt-2 text-muted-foreground">
        Welcome, {user()?.email}. API key management coming soon.
      </p>
    </main>
  );
}
