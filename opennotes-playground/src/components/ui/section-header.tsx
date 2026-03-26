import type { ComponentProps } from "solid-js";
import { splitProps } from "solid-js";
import { cn } from "~/lib/cn";

export default function SectionHeader(
  props: { title: string; subtitle: string } & ComponentProps<"div">,
) {
  const [local, rest] = splitProps(props, ["title", "subtitle", "class"]);
  return (
    <div class={cn("mb-4", local.class)} {...rest}>
      <h2 class="text-xl font-semibold">{local.title}</h2>
      <p class="mt-1 text-sm text-muted-foreground">{local.subtitle}</p>
    </div>
  );
}
