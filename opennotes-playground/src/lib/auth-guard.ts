import { redirect } from "@solidjs/router";
import { getRequestEvent } from "solid-js/web";
import { createClient } from "./supabase-server";

export async function requireAuth() {
  "use server";
  const event = getRequestEvent();
  if (!event) throw new Error("No request event available");
  const supabase = createClient(event.request, event.response.headers);
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    throw redirect("/login");
  }
  return user;
}
