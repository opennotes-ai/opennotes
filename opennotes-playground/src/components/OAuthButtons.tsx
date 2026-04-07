import { createSignal } from "solid-js";
import { Show } from "solid-js";
import { Button } from "~/components/ui/button";
import { Separator } from "~/components/ui/separator";
import { createClient } from "~/lib/supabase-browser";

interface OAuthButtonsProps {
  returnTo?: string;
}

export function OAuthButtons(props: OAuthButtonsProps) {
  const returnTo = () => props.returnTo || "/";
  const [error, setError] = createSignal<string | null>(null);
  const [pending, setPending] = createSignal(false);

  async function signInWith(provider: "google" | "twitter") {
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

  return (
    <div class="space-y-4">
      <Show when={error()}>
        <p class="text-sm text-red-600 dark:text-red-400">{error()}</p>
      </Show>
      <div class="space-y-2">
        <Button
          variant="outline"
          class="w-full"
          disabled={pending()}
          onClick={() => signInWith("google")}
        >
          <GoogleIcon />
          Sign in with Google
        </Button>
        <Button
          variant="outline"
          class="w-full"
          disabled={pending()}
          onClick={() => signInWith("twitter")}
        >
          <XIcon />
          Sign in with X
        </Button>
      </div>
      <div class="relative flex items-center">
        <Separator class="flex-1" />
        <span class="px-3 text-sm text-muted-foreground">or</span>
        <Separator class="flex-1" />
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="currentColor"
    >
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="currentColor"
    >
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
    </svg>
  );
}
