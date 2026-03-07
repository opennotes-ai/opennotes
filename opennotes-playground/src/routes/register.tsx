import { action, useSubmission, A } from "@solidjs/router";
import { Show, createSignal } from "solid-js";
import { getRequestEvent } from "solid-js/web";
import { createClient } from "~/lib/supabase-server";

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
  const submission = useSubmission(registerAction);

  const result = () => submission.result as
    | { error?: string; success?: string }
    | undefined;

  return (
    <main>
      <h1>Sign Up</h1>
      <form action={registerAction} method="post">
        <div>
          <label for="email">Email</label>
          <input id="email" name="email" type="email" required />
        </div>
        <div>
          <label for="password">Password</label>
          <input id="password" name="password" type="password" required />
        </div>
        <div>
          <label for="confirmPassword">Confirm Password</label>
          <input
            id="confirmPassword"
            name="confirmPassword"
            type="password"
            required
          />
        </div>
        <Show when={result()?.error}>
          <p style={{ color: "red" }}>{result()!.error}</p>
        </Show>
        <Show when={result()?.success}>
          <p style={{ color: "green" }}>{result()!.success}</p>
        </Show>
        <button type="submit" disabled={submission.pending}>
          {submission.pending ? "Signing up..." : "Sign Up"}
        </button>
      </form>
      <p>
        Already have an account? <A href="/login">Sign in</A>
      </p>
    </main>
  );
}
