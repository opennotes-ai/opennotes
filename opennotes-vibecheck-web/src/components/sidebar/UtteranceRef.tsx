import type { JSX } from "solid-js";

export interface UtteranceRefProps {
  utteranceId: string;
  onClick: (utteranceId: string) => void;
  label?: string;
  disabled?: boolean;
  class?: string;
  testId?: string;
  ariaLabel?: string;
}

const BASE_CLASS =
  "inline-flex items-center rounded-full bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground";
const ENABLED_CLASS =
  "cursor-pointer border-0 hover:bg-accent hover:text-accent-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1";
const DISABLED_CLASS = "select-none opacity-60";

export default function UtteranceRef(props: UtteranceRefProps): JSX.Element {
  const label = () => props.label ?? `turn ${props.utteranceId}`;
  const classes = () =>
    [BASE_CLASS, props.disabled ? DISABLED_CLASS : ENABLED_CLASS, props.class]
      .filter(Boolean)
      .join(" ");

  if (props.disabled) {
    return (
      <span
        data-testid={props.testId}
        aria-label={props.ariaLabel}
        aria-disabled="true"
        title="Source not available for jump"
        class={classes()}
      >
        {label()}
      </span>
    );
  }

  const activate = (event: Event) => {
    event.preventDefault();
    event.stopPropagation();
    props.onClick(props.utteranceId);
  };

  return (
    <button
      type="button"
      data-testid={props.testId}
      aria-label={props.ariaLabel}
      class={classes()}
      onClick={activate}
      onKeyDown={(event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        activate(event);
      }}
    >
      {label()}
    </button>
  );
}
