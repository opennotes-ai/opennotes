import { A, createAsync, query } from "@solidjs/router";
import { buttonVariants } from "@opennotes/ui/components/ui/button";
import { MarketingHero } from "@opennotes/ui/components/marketing-hero";
import { StepsList } from "@opennotes/ui/components/steps-list";
import { AudienceCard } from "@opennotes/ui/components/audience-card";

const checkLandingRedirect = query(async () => {
  "use server";
  const { redirectIfAuthenticated } = await import("~/lib/auth-guard");
  await redirectIfAuthenticated();
  return null;
}, "landing-redirect");

export const route = {
  preload: () => checkLandingRedirect(),
};

export default function HomePage() {
  // Consume the redirect query in the page body so a stale "anonymous" cache
  // entry is re-evaluated on client navigation (e.g. after login transitions).
  createAsync(() => checkLandingRedirect());

  return (
    <main>
      <MarketingHero
        kicker="Open Notes Platform"
        headline={
          <>
            Community-powered moderation
            <br />
            for forums, Discord, and your own platform.
          </>
        }
        body="Open Notes combines AI classification with community review. Wire it into your platform so flagged content enters a bridging-based review loop, and consensus decisions flow back as moderation actions."
        actions={
          <>
            <A
              href="/register"
              class={buttonVariants({ variant: "default", size: "lg" })}
            >
              Get started
            </A>
            <a
              href="https://docs.opennotes.ai"
              class={buttonVariants({ variant: "link", size: "lg" })}
            >
              Read the docs →
            </a>
          </>
        }
      />

      <section class="px-4 sm:px-6 lg:px-8 py-16 sm:py-24 max-w-5xl mx-auto">
        <header class="mb-12">
          <p class="text-xs uppercase tracking-[0.2em] text-muted-foreground mb-2">
            Get started in minutes
          </p>
          <h2 class="text-3xl font-semibold text-foreground">
            From signup to live moderation in about five minutes
          </h2>
        </header>
        <StepsList
          columns={2}
          steps={[
            {
              title: "Create your account",
              body: "Sign up and register your community on Open Notes.",
            },
            {
              title: "Generate your API key",
              body: "Open the dashboard, click Create Key, choose your platform. Copy your key — you'll only see it once.",
              detail: (
                <code class="text-sm bg-muted text-foreground px-2 py-1 rounded">
                  platform:adapter
                </code>
              ),
            },
            {
              title: "Send your first request",
              body: "Make a simple POST with your API key and a piece of content.",
              detail: (
                <code class="text-sm bg-muted text-foreground px-2 py-1 rounded">
                  POST /api/public/v1/requests
                </code>
              ),
            },
            {
              title: "Get results automatically",
              body: "We process content asynchronously. Poll GET /requests/{id}, or use webhooks (recommended).",
            },
            {
              title: "Plug into your workflow",
              body: "Flag content, surface claims, route edge cases to review. Works with Discourse, Discord, or your own platform.",
            },
          ]}
        />
      </section>

      <section class="px-4 sm:px-6 lg:px-8 py-16 sm:py-24 max-w-5xl mx-auto">
        <header class="mb-10">
          <p class="text-xs uppercase tracking-[0.2em] text-muted-foreground mb-2">
            Who this is for
          </p>
          <h2 class="text-3xl font-semibold text-foreground">Three ways in</h2>
        </header>
        <div class="grid gap-6 sm:grid-cols-3">
          <AudienceCard
            eyebrow="Forum admin"
            title="Running Discourse"
            body="Install, configure, or troubleshoot the Open Notes plugin on your Discourse forum."
            href="https://docs.opennotes.ai/existing-integrations/discourse/overview"
            linkLabel="Discourse setup"
          />
          <AudienceCard
            eyebrow="Engineer"
            title="Build an integration"
            body="Wire Open Notes into a new platform. Concepts, onboarding, and the end-to-end walkthrough — from your first request to receiving consensus decisions back."
            href="https://docs.opennotes.ai/integration-guide/overview"
            linkLabel="Integration guide"
          />
          <AudienceCard
            eyebrow="API consumer"
            title="Endpoint reference"
            body="Already have a key? Jump to the OpenAPI reference."
            href="https://docs.opennotes.ai/api-reference/overview"
            linkLabel="API reference"
          />
        </div>
      </section>

      <section class="px-4 sm:px-6 lg:px-8 py-16 sm:py-24 max-w-5xl mx-auto border-t border-border">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
          <div>
            <h2 class="text-2xl font-semibold text-foreground">Ready to ship?</h2>
            <p class="mt-2 text-muted-foreground">
              Spin up an API key and send your first request in under five minutes.
            </p>
          </div>
          <div class="flex gap-3">
            <A
              href="/register"
              class={buttonVariants({ variant: "default", size: "lg" })}
            >
              Sign Up
            </A>
            <A
              href="/login"
              class={buttonVariants({ variant: "ghost", size: "lg" })}
            >
              Sign In
            </A>
          </div>
        </div>
      </section>
    </main>
  );
}
