import type { JSX } from "solid-js";
import { For, Show, splitProps } from "solid-js";
import { cn } from "../utils";

export type Step = {
  title: string;
  body: JSX.Element | string;
  detail?: JSX.Element;
};

export type StepsListProps = {
  steps: Step[];
  columns?: 1 | 2;
  class?: string;
};

export function StepsList(props: StepsListProps): JSX.Element {
  const [local, others] = splitProps(props, ["steps", "columns", "class"]);
  const columns = () => local.columns ?? 1;
  return (
    <ol
      class={cn(
        "grid gap-y-10 sm:gap-y-12",
        columns() === 2 ? "sm:grid-cols-2 sm:gap-x-12" : "",
        local.class,
      )}
      {...others}
    >
      <For each={local.steps}>
        {(step, index) => (
          <li class="grid grid-cols-[auto_1fr] gap-x-6 sm:gap-x-8">
            <span
              aria-hidden="true"
              class="font-black text-5xl tabular-nums leading-none text-muted-foreground/70"
            >
              {(index() + 1).toString().padStart(2, "0")}
            </span>
            <div>
              <h3 class="text-lg font-semibold mb-2 text-foreground">{step.title}</h3>
              <div class="text-muted-foreground leading-relaxed max-w-[70ch]">
                {step.body}
              </div>
              <Show when={step.detail}>
                <div class="mt-3">{step.detail}</div>
              </Show>
            </div>
          </li>
        )}
      </For>
    </ol>
  );
}
