import type { JSX } from "solid-js";
import { Show, splitProps } from "solid-js";
import { cn } from "../utils";

export type MarketingHeroProps = {
  kicker?: string;
  headline: JSX.Element | string;
  body: JSX.Element | string;
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
          class="text-foreground font-extrabold"
          style={{
            "font-size": "clamp(2.25rem, 4vw + 1rem, 4.5rem)",
            "line-height": "1.05",
            "letter-spacing": "-0.02em",
          }}
        >
          {local.headline}
        </h1>
        <p class="mt-6 max-w-[70ch] text-lg text-muted-foreground leading-relaxed">
          {local.body}
        </p>
        <Show when={local.actions}>
          <div class="mt-10 flex flex-wrap items-center gap-4">{local.actions}</div>
        </Show>
      </div>
    </section>
  );
}
