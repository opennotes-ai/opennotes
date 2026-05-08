import { createSignal, type JSX } from "solid-js";
import { ThumbsUp, ThumbsDown, MessageSquare } from "lucide-solid";
import { Popover, PopoverContent } from "@opennotes/ui";
import { FeedbackSurface } from "./FeedbackSurface";
import { type FeedbackType } from "./FeedbackForm";
import {
  openFeedback,
  submitFeedback,
  submitFeedbackCombined,
  type OpenInput,
  type CombinedInput,
} from "../../lib/feedback-client";
import type { components } from "../../lib/generated-types";

type SubmitReq = components["schemas"]["FeedbackSubmitRequest"];
type OpenRes = components["schemas"]["FeedbackOpenResponse"];

interface FeedbackPopoverProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isDesktop: boolean;
  bellLocation: string;
  children: JSX.Element;
}

const OPEN_POST_GATE_TIMEOUT_MS = 800;

export function FeedbackPopover(props: FeedbackPopoverProps): JSX.Element {
  const [surfaceOpen, setSurfaceOpen] = createSignal(false);
  const [initialType, setInitialType] = createSignal<FeedbackType>("thumbs_up");
  const [feedbackId, setFeedbackId] = createSignal<string | null>(null);
  const [openPayload, setOpenPayload] = createSignal<OpenInput>({
    page_path: "",
    user_agent: "",
    referrer: "",
    bell_location: props.bellLocation,
    initial_type: "thumbs_up",
  });

  let openInFlight: Promise<string | null> | null = null;
  let openController: AbortController | null = null;
  let generation = 0;

  const handleIconClick = async (type: FeedbackType) => {
    setFeedbackId(null);
    props.onOpenChange(false);

    if (openController !== null) {
      openController.abort();
      openController = null;
    }

    const thisGeneration = ++generation;

    const payload: OpenInput = {
      page_path: window.location.pathname,
      user_agent: navigator.userAgent,
      referrer: document.referrer,
      bell_location: props.bellLocation,
      initial_type: type,
    };

    setInitialType(type);
    setOpenPayload(payload);
    setSurfaceOpen(true);

    const controller = new AbortController();
    openController = controller;

    const runOpen = async (): Promise<string | null> => {
      try {
        const result = await openFeedback(payload, controller.signal);
        if (thisGeneration === generation) {
          setFeedbackId(result.id);
        }
        return result.id;
      } catch {
        if (thisGeneration === generation) {
          setFeedbackId(null);
        }
        return null;
      } finally {
        if (openController === controller) {
          openController = null;
        }
      }
    };
    const flight = runOpen();
    openInFlight = flight;
    flight.finally(() => {
      if (openInFlight === flight) {
        openInFlight = null;
      }
    });
    await flight;
  };

  const wrappedSubmitFeedback = async (
    id: string,
    payload: SubmitReq,
  ): Promise<void> => {
    return submitFeedback(id, payload);
  };

  const wrappedSubmitFeedbackCombined = async (
    payload: CombinedInput,
  ): Promise<OpenRes> => {
    if (openInFlight !== null) {
      const inFlight = openInFlight;
      const resolvedId = await Promise.race<string | null>([
        inFlight,
        new Promise<null>((resolve) =>
          setTimeout(() => resolve(null), OPEN_POST_GATE_TIMEOUT_MS),
        ),
      ]);
      if (resolvedId !== null) {
        await submitFeedback(resolvedId, {
          email: payload.email,
          message: payload.message,
          final_type: payload.final_type,
        });
        return { id: resolvedId };
      }
    }
    return submitFeedbackCombined(payload);
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
        submitFeedback={wrappedSubmitFeedback}
        submitFeedbackCombined={wrappedSubmitFeedbackCombined}
      />
    </>
  );
}
