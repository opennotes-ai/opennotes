import { action, redirect, useSubmission, A } from "@solidjs/router";
import { Show } from "solid-js";
import { getRequestEvent } from "solid-js/web";
import { createClient } from "~/lib/supabase-server";
import { Button } from "@opennotes/ui/components/ui/button";
import { Input } from "@opennotes/ui/components/ui/input";

const loginAction = action(async (formData: FormData) => {
  "use server";
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");

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

  throw redirect("/dashboard");
}, "login");

export default function LoginPage() {
  const submission = useSubmission(loginAction);

  return (
    <main class="mx-auto max-w-sm px-4 py-12">
      <h1 class="text-2xl font-bold tracking-tight">Sign In</h1>
      <form action={loginAction} method="post" class="mt-6 space-y-4">
        <div class="space-y-1.5">
          <label for="email" class="text-sm font-medium">Email</label>
          <Input id="email" name="email" type="email" required />
        </div>
        <div class="space-y-1.5">
          <label for="password" class="text-sm font-medium">Password</label>
          <Input id="password" name="password" type="password" required />
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
        <A href="/register" class="text-primary hover:underline">Sign up</A>
      </p>
    </main>
  );
}
