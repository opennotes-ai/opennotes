import { createSignal, onMount, onCleanup, type JSX } from "solid-js";
import ConciergeBell from "lucide-solid/icons/concierge-bell";
import { cn, PopoverTrigger } from "@opennotes/ui";
import { FeedbackPopover } from "./FeedbackPopover";

export interface FeedbackBellProps {
  bell_location: string;
  ariaContext?: string;
  class?: string;
}

export function FeedbackBell(props: FeedbackBellProps): JSX.Element {
  const [popoverOpen, setPopoverOpen] = createSignal(false);
  const [isDesktop, setIsDesktop] = createSignal(false);

  let hoverTimer: ReturnType<typeof setTimeout> | undefined;

  onMount(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    setIsDesktop(mq.matches);

    const handleChange = (e: MediaQueryListEvent) => {
      setIsDesktop(e.matches);
    };
    mq.addEventListener("change", handleChange);

    onCleanup(() => {
      mq.removeEventListener("change", handleChange);
      if (hoverTimer !== undefined) {
        clearTimeout(hoverTimer);
      }
    });
  });

  const handleMouseEnter = () => {
    if (!isDesktop()) return;
    hoverTimer = setTimeout(() => {
      setPopoverOpen(true);
    }, 150);
  };

  const handleMouseLeave = () => {
    if (hoverTimer !== undefined) {
      clearTimeout(hoverTimer);
      hoverTimer = undefined;
    }
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      setPopoverOpen(false);
    }
  };

  const ariaLabel = () =>
    `Send feedback about ${props.ariaContext ?? props.bell_location}`;

  return (
    <FeedbackPopover
      open={popoverOpen()}
      onOpenChange={setPopoverOpen}
      isDesktop={isDesktop()}
      bellLocation={props.bell_location}
    >
      <PopoverTrigger
        as="button"
        type="button"
        aria-label={ariaLabel()}
        class={cn(
          "absolute right-2 bottom-2 text-muted-foreground opacity-50 transition-opacity hover:opacity-100 focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 rounded-sm",
          props.class,
        )}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onKeyDown={handleKeyDown}
      >
        <ConciergeBell size={16} />
      </PopoverTrigger>
    </FeedbackPopover>
  );
}
