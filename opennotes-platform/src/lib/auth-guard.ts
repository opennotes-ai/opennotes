import { redirect } from "@solidjs/router";
import { getRequestEvent } from "solid-js/web";

export async function requireAuth() {
  "use server";
  const event = getRequestEvent();
  if (!event || !event.locals.user) {
    throw redirect("/login");
  }
  return event.locals.user;
}

export async function redirectIfAuthenticated(target = "/dashboard") {
  "use server";
  const event = getRequestEvent();
  if (!event) return;
  if (event.locals.user) {
    throw redirect(target);
  }
}
