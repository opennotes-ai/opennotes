import { action, query, createAsync, redirect, useSubmission, A } from "@solidjs/router";
import { Show, Suspense } from "solid-js";
import { getRequestEvent } from "solid-js/web";
import { createClient } from "~/lib/supabase-server";

const getAuthUser = query(async () => {
  "use server";
  const event = getRequestEvent();
  if (!event) return null;
  const supabase = createClient(event.request, event.response.headers);
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;
  return { email: user.email };
}, "authUser");

const signOutAction = action(async () => {
  "use server";
  const event = getRequestEvent();
  if (!event) throw new Error("No request event available");
  const supabase = createClient(event.request, event.response.headers);
  await supabase.auth.signOut();
  throw redirect("/login");
}, "signOut");

export default function AuthStatus() {
  const user = createAsync(() => getAuthUser());
  const signOut = useSubmission(signOutAction);

  return (
    <Suspense>
      <Show
        when={user()}
        fallback={<A href="/login">Sign in</A>}
      >
        {(u) => (
          <span>
            {u().email}{" "}
            <form action={signOutAction} method="post" style={{ display: "inline" }}>
              <button type="submit" disabled={signOut.pending}>
                Sign out
              </button>
            </form>
          </span>
        )}
      </Show>
    </Suspense>
  );
}
