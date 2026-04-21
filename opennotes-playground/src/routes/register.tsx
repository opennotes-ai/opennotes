import { action, useSubmission, useSearchParams, A } from "@solidjs/router";
import { Show } from "solid-js";
import { getRequestEvent } from "solid-js/web";
import { createClient } from "~/lib/supabase-server";
import { Button } from "@opennotes/ui/components/ui/button";
import { Input } from "@opennotes/ui/components/ui/input";
import { OAuthButtons } from "~/components/OAuthButtons";

const registerAction = action(async (formData: FormData) => {
  "use server";
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  const confirmPassword = String(formData.get("confirmPassword") ?? "");

  if (!email || !password) {
    return { error: "Email and password are required." };
  }

  if (password !== confirmPassword) {
    return { error: "Passwords do not match." };
  }

  if (password.length < 6) {
    return { error: "Password must be at least 6 characters." };
  }

  const event = getRequestEvent();
  if (!event) throw new Error("No request event available");

  const supabase = createClient(event.request, event.response.headers);
  const { error } = await supabase.auth.signUp({ email, password });

  if (error) {
    return { error: error.message };
  }

  return { success: "Check your email to confirm your account." };
}, "register");

export default function RegisterPage() {
  const [searchParams] = useSearchParams();
  const submission = useSubmission(registerAction);

  const result = () => submission.result as
    | { error?: string; success?: string }
    | undefined;

  return (
    <main class="mx-auto max-w-sm px-4 py-12">
      <h1 class="text-2xl font-bold tracking-tight">Sign Up</h1>
      <div class="mt-6">
        <OAuthButtons returnTo={searchParams.returnTo as string | undefined} />
      </div>
      <form action={registerAction} method="post" class="mt-4 space-y-4">
        <div class="space-y-1.5">
          <label for="email" class="text-sm font-medium">Email</label>
          <Input id="email" name="email" type="email" required />
        </div>
        <div class="space-y-1.5">
          <label for="password" class="text-sm font-medium">Password</label>
          <Input id="password" name="password" type="password" required />
        </div>
        <div class="space-y-1.5">
          <label for="confirmPassword" class="text-sm font-medium">Confirm Password</label>
          <Input id="confirmPassword" name="confirmPassword" type="password" required />
        </div>
        <Show when={result()?.error}>
          <p class="text-sm text-red-600 dark:text-red-400">{result()!.error}</p>
        </Show>
        <Show when={result()?.success}>
          <p class="text-sm text-emerald-600 dark:text-emerald-400">{result()!.success}</p>
        </Show>
        <Button type="submit" class="w-full" disabled={submission.pending}>
          {submission.pending ? "Signing up..." : "Sign Up"}
        </Button>
      </form>
      <p class="mt-4 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <A
          href={searchParams.returnTo ? `/login?returnTo=${encodeURIComponent(String(searchParams.returnTo))}` : "/login"}
          class="text-primary hover:underline"
        >
          Sign in
        </A>
      </p>
    </main>
  );
}
