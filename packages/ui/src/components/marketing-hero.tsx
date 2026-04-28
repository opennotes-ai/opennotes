import type { JSX } from "solid-js";
import { Show, splitProps } from "solid-js";
import { cn } from "../utils";

export type MarketingHeroProps = {
  kicker?: string;
  headline: JSX.Element | string;
  // String-only because body renders inside a <p>; passing block JSX would
  // produce invalid HTML and reparent during hydration.
  body: string;
  actions?: JSX.Element;
  class?: string;
};

export function MarketingHero(props: MarketingHeroProps): JSX.Element {
  const [local, others] = splitProps(props, ["kicker", "headline", "body", "actions", "class"]);
  return (
    <section
      class={cn("px-4 sm:px-6 lg:px-8 py-16 sm:py-24 lg:py-32", local.class)}
      {...others}
    >
      <div class="mx-auto max-w-5xl text-left">
        <Show when={local.kicker}>
          <p class="text-xs uppercase tracking-[0.2em] text-muted-foreground mb-4">
            {local.kicker}
          </p>
        </Show>
        <h1
          class="text-foreground font-bold"
          style={{
            "font-size": "clamp(2.25rem, 3vw + 1rem, 3.5rem)",
            "line-height": "1.1",
            "letter-spacing": "-0.01em",
          }}
        >
          {local.headline}
        </h1>
        <p class="mt-6 max-w-[70ch] text-lg text-muted-foreground leading-relaxed">
          {local.body}
        </p>
        <div class="mt-10 flex flex-wrap items-center gap-4">
          {local.actions}
        </div>
      </div>
    </section>
  );
}
