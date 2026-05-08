import type { JSX } from "solid-js";
import HelpCircle from "lucide-solid/icons/help-circle";
import { cn } from "@opennotes/ui";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@opennotes/ui/components/ui/popover";

const TOOLTIP_COPY = {
  truth:
    "Epistemic stance, not verdict. Whether claims are sourced, first-person, second-hand, or actively misleading — how the knowledge is held, regardless of whether it's ultimately right.",
  relevance:
    "How tightly the discussion is tethered to the source. Insightful engagement, on-topic chatter, drift, or full topic abandonment.",
  sentiment:
    "The emotional register of the conversation. Read alongside the other axes; tone alone doesn't tell you much.",
} as const;

export function WeatherHelpButton(props: { class?: string }): JSX.Element {
  return (
    <Popover>
      <PopoverTrigger
        as="button"
        type="button"
        aria-label="Explain weather report axes"
        class={cn(
          "absolute right-2 bottom-2 text-muted-foreground opacity-50 transition-opacity hover:opacity-100 focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 rounded-sm",
          props.class,
        )}
      >
        <HelpCircle class="size-4" aria-hidden="true" />
      </PopoverTrigger>
      <PopoverContent class="max-w-xs space-y-3 text-sm leading-snug">
        <p>
          <span class="font-semibold">Truth</span> — {TOOLTIP_COPY.truth}
        </p>
        <p>
          <span class="font-semibold">Relevance</span> — {TOOLTIP_COPY.relevance}
        </p>
        <p>
          <span class="font-semibold">Sentiment</span> — {TOOLTIP_COPY.sentiment}
        </p>
      </PopoverContent>
    </Popover>
  );
}
