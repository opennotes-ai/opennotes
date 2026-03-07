import { action, redirect, useSubmission, A } from "@solidjs/router";
import { Show } from "solid-js";
import { getRequestEvent } from "solid-js/web";
import { createClient } from "~/lib/supabase-server";

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

  throw redirect("/");
}, "login");

export default function LoginPage() {
  const submission = useSubmission(loginAction);

  return (
    <main>
      <h1>Sign In</h1>
      <form action={loginAction} method="post">
        <div>
          <label for="email">Email</label>
          <input id="email" name="email" type="email" required />
        </div>
        <div>
          <label for="password">Password</label>
          <input id="password" name="password" type="password" required />
        </div>
        <Show when={submission.result}>
          <p style={{ color: "red" }}>{submission.result}</p>
        </Show>
        <button type="submit" disabled={submission.pending}>
          {submission.pending ? "Signing in..." : "Sign In"}
        </button>
      </form>
      <p>
        Don't have an account? <A href="/register">Sign up</A>
      </p>
    </main>
  );
}
