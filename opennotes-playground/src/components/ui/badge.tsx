import type { ComponentProps } from "solid-js";
import type { VariantProps } from "cva";
import { cva } from "~/lib/cva";

export const badgeVariants = cva({
  base: "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold transition-colors",
  variants: {
    variant: {
      default: "bg-primary/15 text-primary dark:bg-primary/25",
      success:
        "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
      warning:
        "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
      danger:
        "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
      info: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
      muted:
        "bg-muted text-muted-foreground",
      indigo:
        "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

export type BadgeVariant = NonNullable<
  VariantProps<typeof badgeVariants>["variant"]
>;

export function Badge(
  props: ComponentProps<"span"> & VariantProps<typeof badgeVariants>,
) {
  return (
    <span
      class={badgeVariants({ variant: props.variant, class: props.class })}
    >
      {props.children}
    </span>
  );
}
