declare namespace App {
  interface RequestEventLocals {
    user: import("@supabase/supabase-js").User | null;
    supabase: import("@supabase/supabase-js").SupabaseClient;
  }
}
