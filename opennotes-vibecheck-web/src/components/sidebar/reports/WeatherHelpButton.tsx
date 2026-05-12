import type { JSX } from "solid-js";
import HelpCircle from "lucide-solid/icons/help-circle";
import { cn } from "@opennotes/ui";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@opennotes/ui/components/ui/popover";
import { AXIS_DEFINITIONS } from "~/lib/weather-labels";

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
          <span class="font-semibold">Truth</span> — {AXIS_DEFINITIONS.truth.description}
        </p>
        <p>
          <span class="font-semibold">Relevance</span> — {AXIS_DEFINITIONS.relevance.description}
        </p>
        <p>
          <span class="font-semibold">Sentiment</span> — {AXIS_DEFINITIONS.sentiment.description}
        </p>
      </PopoverContent>
    </Popover>
  );
}
