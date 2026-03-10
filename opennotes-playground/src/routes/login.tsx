import { action, redirect, useSubmission, useSearchParams, A } from "@solidjs/router";
import { Show } from "solid-js";
import { getRequestEvent } from "solid-js/web";
import { createClient } from "~/lib/supabase-server";
import { safeRedirectPath } from "~/lib/safe-redirect";
import { Button } from "~/components/ui/button";

const loginAction = action(async (formData: FormData) => {
  "use server";
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  const returnTo = safeRedirectPath(formData.get("returnTo") as string | null);

  if (!email || !password) {
    return "Email and password are required.";
  }

  const event = getRequestEvent();
  if (!event) throw new Error("No request event available");

  const supabase = createClient(event.request, event.response.headers);
  const { error } = await supabase.auth.signInWithPassword({ email, password });

  if (error) {
    return error.message;
  }

  throw redirect(returnTo, { revalidate: ["analysis", "detailed-analysis", "authUser"] });
}, "login");

export default function LoginPage() {
  const [searchParams] = useSearchParams();
  const submission = useSubmission(loginAction);

  return (
    <main class="mx-auto max-w-sm px-4 py-12">
      <h1 class="text-2xl font-bold tracking-tight">Sign In</h1>
      <form action={loginAction} method="post" class="mt-6 space-y-4">
        <input type="hidden" name="returnTo" value={searchParams.returnTo ?? ""} />
        <div class="space-y-1.5">
          <label for="email" class="text-sm font-medium">Email</label>
          <input
            id="email"
            name="email"
            type="email"
            required
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30"
          />
        </div>
        <div class="space-y-1.5">
          <label for="password" class="text-sm font-medium">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            required
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30"
          />
        </div>
        <Show when={submission.result}>
          <p class="text-sm text-red-600 dark:text-red-400">{submission.result}</p>
        </Show>
        <Button type="submit" class="w-full" disabled={submission.pending}>
          {submission.pending ? "Signing in..." : "Sign In"}
        </Button>
      </form>
      <p class="mt-4 text-center text-sm text-muted-foreground">
        Don't have an account?{" "}
        <A
          href={searchParams.returnTo ? `/register?returnTo=${encodeURIComponent(String(searchParams.returnTo))}` : "/register"}
          class="text-primary hover:underline"
        >
          Sign up
        </A>
      </p>
    </main>
  );
}
