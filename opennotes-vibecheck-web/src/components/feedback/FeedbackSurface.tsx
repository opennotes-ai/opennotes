import { Show, type JSX } from "solid-js";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from "@opennotes/ui";
import { FeedbackForm, type FeedbackType } from "./FeedbackForm";
import type {
  submitFeedback,
  submitFeedbackCombined,
  OpenInput,
} from "../../lib/feedback-client";

export interface FeedbackSurfaceProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isDesktop: boolean;
  initialType: FeedbackType;
  feedbackId: string | null;
  openPayload: OpenInput;
  submitFeedback: typeof submitFeedback;
  submitFeedbackCombined: typeof submitFeedbackCombined;
}

export function FeedbackSurface(props: FeedbackSurfaceProps): JSX.Element {
  const handleSend = async (payload: {
    email: string | null;
    message: string | null;
    final_type: FeedbackType;
  }) => {
    if (props.feedbackId !== null) {
      await props.submitFeedback(props.feedbackId, {
        email: payload.email,
        message: payload.message,
        final_type: payload.final_type,
      });
    } else {
      await props.submitFeedbackCombined({
        ...props.openPayload,
        email: payload.email,
        message: payload.message,
        final_type: payload.final_type,
      });
    }
    props.onOpenChange(false);
  };

  const handleCancel = () => {
    props.onOpenChange(false);
  };

  return (
    <Show
      when={props.isDesktop}
      fallback={
        <Drawer open={props.open} onOpenChange={props.onOpenChange}>
          <DrawerContent>
            <DrawerHeader>
              <DrawerTitle>Send feedback</DrawerTitle>
            </DrawerHeader>
            <FeedbackForm
              initialType={props.initialType}
              onSend={handleSend}
              onCancel={handleCancel}
            />
          </DrawerContent>
        </Drawer>
      }
    >
      <Dialog open={props.open} onOpenChange={props.onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send feedback</DialogTitle>
          </DialogHeader>
          <FeedbackForm
            initialType={props.initialType}
            onSend={handleSend}
            onCancel={handleCancel}
          />
        </DialogContent>
      </Dialog>
    </Show>
  );
}
