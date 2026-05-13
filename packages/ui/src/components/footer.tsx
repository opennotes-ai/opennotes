import type { JSX } from "solid-js";
import { cn } from "../utils";

export type FooterProps = {
  class?: string;
};

export function Footer(props: FooterProps): JSX.Element {
  return (
    <footer
      class={cn(
        "flex items-center justify-between border-t border-border bg-background px-4 py-4 sm:px-6 lg:px-8",
        props.class,
      )}
    >
      <p class="text-sm text-muted-foreground">
        © {new Date().getFullYear()} Open Notes. All rights reserved.
      </p>
      <nav aria-label="Footer navigation" class="flex items-center gap-4">
        <a
          href="https://opennotes.ai/privacy"
          target="_blank"
          rel="noopener noreferrer"
          class="text-sm text-muted-foreground transition-colors hover:text-primary"
        >
          Privacy
        </a>
        <a
          href="https://opennotes.ai/terms"
          target="_blank"
          rel="noopener noreferrer"
          class="text-sm text-muted-foreground transition-colors hover:text-primary"
        >
          Terms
        </a>
      </nav>
    </footer>
  );
}
