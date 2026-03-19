import { redirect } from "@solidjs/router";
import { getRequestEvent } from "solid-js/web";

export async function requireAuth() {
  "use server";
  const event = getRequestEvent();
  if (!event?.locals.user) {
    throw redirect("/login");
  }
  return event.locals.user;
}
