import { createSignal } from "solid-js";
import { OAuthButtonsRow, type OAuthProvider } from "@opennotes/ui/components/oauth-buttons-row";
import { createClient } from "~/lib/supabase-browser";

interface OAuthButtonsProps {
  returnTo?: string;
}

export function OAuthButtons(props: OAuthButtonsProps) {
  const returnTo = () => props.returnTo || "/";
  const [error, setError] = createSignal<string | null>(null);
  const [pending, setPending] = createSignal(false);

  async function signInWith(provider: OAuthProvider) {
    setError(null);
    setPending(true);
    try {
      const supabase = createClient();
      const redirectTo = `${window.location.origin}/auth/callback?next=${encodeURIComponent(returnTo())}`;
      const { error: oauthError } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo,
          ...(provider === "twitter" && { scopes: "users.read" }),
        },
      });
      if (oauthError) {
        setError(oauthError.message);
      }
    } catch {
      setError("Failed to start sign-in. Please try again.");
    } finally {
      setPending(false);
    }
  }

  return <OAuthButtonsRow onSignIn={signInWith} pending={pending()} error={error()} />;
}
