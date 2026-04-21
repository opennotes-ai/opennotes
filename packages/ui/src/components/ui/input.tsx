import type { ComponentProps } from "solid-js";
import { splitProps } from "solid-js";
import { cn } from "../../utils";

export function Input(props: ComponentProps<"input">) {
  const [local, rest] = splitProps(props, ["class"]);
  return (
    <input
      class={cn(
        "w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid]:border-destructive aria-[invalid]:ring-destructive/30",
        local.class,
      )}
      {...rest}
    />
  );
}
