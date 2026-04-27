import type { JSX } from "solid-js";
import { splitProps } from "solid-js";
import { cn } from "../utils";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "./ui/card";

export type AudienceCardProps = {
  icon?: JSX.Element;
  eyebrow: string;
  title: string;
  // String-only because body renders inside a <p>; passing block JSX would
  // produce invalid HTML and reparent during hydration. Also avoids a
  // nested-interactive-content footgun, since the whole card is an <a>.
  body: string;
  href: string;
  linkLabel?: string;
  class?: string;
};

export function AudienceCard(props: AudienceCardProps): JSX.Element {
  const [local, others] = splitProps(props, [
    "icon",
    "eyebrow",
    "title",
    "body",
    "href",
    "linkLabel",
    "class",
  ]);
  return (
    <a
      href={local.href}
      class={cn(
        "block rounded-lg outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        local.class,
      )}
      {...others}
    >
      <Card class="h-full transition-colors hover:border-foreground/30">
        <CardHeader>
          <div class="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
            <span class="inline-flex items-center empty:hidden">{local.icon}</span>
            <span>{local.eyebrow}</span>
          </div>
          <CardTitle class="mt-3 text-xl font-semibold">{local.title}</CardTitle>
        </CardHeader>
        <CardContent>
          <p class="text-muted-foreground leading-relaxed">{local.body}</p>
        </CardContent>
        <CardFooter>
          <span class="inline-flex items-center gap-2 text-sm font-medium text-foreground">
            {local.linkLabel ?? "Learn more"}
            <span aria-hidden="true">→</span>
          </span>
        </CardFooter>
      </Card>
    </a>
  );
}
