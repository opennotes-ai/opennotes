import { createMiddleware } from "@solidjs/start/middleware";
import { createClient } from "~/lib/supabase-server";

export default createMiddleware({
  onRequest: async (event) => {
    const supabase = createClient(event.request, event.response.headers);
    await supabase.auth.getUser();
  },
});
