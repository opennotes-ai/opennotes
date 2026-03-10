import { query, createAsync, redirect } from "@solidjs/router";
import { getRequestEvent } from "solid-js/web";

const redirectToHome = query(async () => {
  "use server";
  const event = getRequestEvent();
  const url = new URL(event?.request.url ?? "/");
  const target = url.search ? `/${url.search}` : "/";
  throw redirect(target, 301);
}, "simulations-redirect");

export default function SimulationsIndex() {
  createAsync(() => redirectToHome());
  return null;
}
