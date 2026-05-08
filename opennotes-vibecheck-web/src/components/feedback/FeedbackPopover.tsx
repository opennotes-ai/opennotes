import { createSignal, type JSX } from "solid-js";
import { ThumbsUp, ThumbsDown, MessageSquare } from "lucide-solid";
import { Popover, PopoverContent } from "@opennotes/ui";
import { FeedbackSurface } from "./FeedbackSurface";
import { type FeedbackType } from "./FeedbackForm";
import {
  openFeedback,
  submitFeedback,
  submitFeedbackCombined,
} from "../../lib/feedback-client";
import type { components } from "../../lib/generated-types";

type OpenReq = components["schemas"]["FeedbackOpenRequest"];

interface FeedbackPopoverProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isDesktop: boolean;
  bellLocation: string;
  children: JSX.Element;
}

export function FeedbackPopover(props: FeedbackPopoverProps): JSX.Element {
  const [surfaceOpen, setSurfaceOpen] = createSignal(false);
  const [initialType, setInitialType] = createSignal<FeedbackType>("thumbs_up");
  const [feedbackId, setFeedbackId] = createSignal<string | null>(null);
  const [openPayload, setOpenPayload] = createSignal<OpenReq>({
    page_path: "",
    user_agent: "",
    referrer: "",
    bell_location: props.bellLocation,
    initial_type: "thumbs_up",
  });

  const handleIconClick = async (type: FeedbackType) => {
    props.onOpenChange(false);

    const payload: OpenReq = {
      page_path: window.location.pathname,
      user_agent: navigator.userAgent,
      referrer: document.referrer,
      bell_location: props.bellLocation,
      initial_type: type,
    };

    setInitialType(type);
    setOpenPayload(payload);
    setSurfaceOpen(true);

    try {
      const result = await openFeedback(payload);
      setFeedbackId(result.id);
    } catch {
      setFeedbackId(null);
    }
  };

  return (
    <>
      <Popover open={props.open} onOpenChange={props.onOpenChange} placement="top">
        {props.children}
        <PopoverContent class="w-auto p-2">
          <div class="flex items-center gap-2">
            <button
              type="button"
              aria-label="Thumbs up"
              class="flex h-10 w-10 items-center justify-center rounded-md hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              onClick={() => handleIconClick("thumbs_up")}
            >
              <ThumbsUp size={20} />
            </button>
            <button
              type="button"
              aria-label="Thumbs down"
              class="flex h-10 w-10 items-center justify-center rounded-md hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              onClick={() => handleIconClick("thumbs_down")}
            >
              <ThumbsDown size={20} />
            </button>
            <button
              type="button"
              aria-label="Send a message"
              class="flex h-10 w-10 items-center justify-center rounded-md hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              onClick={() => handleIconClick("message")}
            >
              <MessageSquare size={20} />
            </button>
          </div>
        </PopoverContent>
      </Popover>

      <FeedbackSurface
        open={surfaceOpen()}
        onOpenChange={setSurfaceOpen}
        isDesktop={props.isDesktop}
        initialType={initialType()}
        feedbackId={feedbackId()}
        openPayload={openPayload()}
        submitFeedback={submitFeedback}
        submitFeedbackCombined={submitFeedbackCombined}
      />
    </>
  );
}
