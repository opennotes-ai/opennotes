import { createMiddleware } from "@solidjs/start/middleware";
import { createClient, createReadOnlyClient } from "~/lib/supabase-server";

export default createMiddleware({
  onRequest: async (event) => {
    try {
      const supabase = createClient(event.request, event.response.headers);
      const { data: { user } } = await supabase.auth.getUser();
      event.locals.user = user ?? null;
    } catch (err) {
      console.error("Middleware auth error:", err);
      event.locals.user = null;
    } finally {
      event.locals.supabase = createReadOnlyClient(event.request);
    }
  },
});
