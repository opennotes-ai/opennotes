import { Show } from "solid-js";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@opennotes/ui/components/ui/popover";

const TRUNCATE_CHAR_THRESHOLD = 140;

const CLAMP_BY_LINES: Record<2 | 3 | 4, string> = {
  2: "line-clamp-2",
  3: "line-clamp-3",
  4: "line-clamp-4",
};

export interface ExpandableTextProps {
  text: string;
  lines?: 2 | 3 | 4;
  class?: string;
  testId?: string;
}

function isLongText(text: string): boolean {
  return text.length > TRUNCATE_CHAR_THRESHOLD || text.includes("\n");
}

export default function ExpandableText(props: ExpandableTextProps) {
  const lines = () => props.lines ?? 2;
  const clamp = () => CLAMP_BY_LINES[lines()];
  const long = () => isLongText(props.text);

  return (
    <Show
      when={long()}
      fallback={
        <p data-testid={props.testId} class={props.class}>
          {props.text}
        </p>
      }
    >
      <Popover>
        <PopoverTrigger
          aria-label="Show full text"
          class="block w-full cursor-pointer rounded-sm text-left outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
        >
          <p
            data-testid={props.testId}
            data-truncated="true"
            class={`${props.class ?? ""} ${clamp()}`}
          >
            {props.text}
          </p>
        </PopoverTrigger>
        <PopoverContent
          data-testid="expandable-text-content"
          class="max-w-md whitespace-pre-wrap text-sm leading-relaxed"
        >
          {props.text}
        </PopoverContent>
      </Popover>
    </Show>
  );
}
