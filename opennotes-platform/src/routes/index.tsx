import { A, createAsync, query } from "@solidjs/router";

const checkLandingRedirect = query(async () => {
  "use server";
  const { redirectIfAuthenticated } = await import("~/lib/auth-guard");
  await redirectIfAuthenticated();
  return null;
}, "landing-redirect");

export const route = {
  preload: () => checkLandingRedirect(),
};

export default function HomePage() {
  createAsync(() => checkLandingRedirect());

  return (
    <main class="mx-auto max-w-2xl px-4 py-16 text-center">
      <h1 class="text-4xl font-bold tracking-tight">Open Notes Platform</h1>
      <p class="mt-4 text-lg text-muted-foreground">
        Generate and manage API keys for the Open Notes API.
      </p>
      <div class="mt-8 flex justify-center gap-4">
        <A href="/login" class="rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90">
          Sign In
        </A>
        <A href="/register" class="rounded-md border border-border px-6 py-2.5 text-sm font-medium hover:bg-accent">
          Sign Up
        </A>
      </div>
    </main>
  );
}
