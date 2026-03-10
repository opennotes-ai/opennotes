import { action, query, createAsync, redirect, useSubmission, A } from "@solidjs/router";
import { Show, Suspense } from "solid-js";
import { getRequestEvent } from "solid-js/web";
import { createClient } from "~/lib/supabase-server";
import { Button } from "~/components/ui/button";

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
        fallback={
          <Button variant="ghost" size="sm" as={A} href="/login">
            Sign in
          </Button>
        }
      >
        {(u) => (
          <span class="flex items-center gap-2 text-sm">
            <span class="text-muted-foreground">{u().email}</span>
            <form action={signOutAction} method="post" class="inline">
              <Button variant="ghost" size="sm" type="submit" disabled={signOut.pending}>
                Sign out
              </Button>
            </form>
          </span>
        )}
      </Show>
    </Suspense>
  );
}
