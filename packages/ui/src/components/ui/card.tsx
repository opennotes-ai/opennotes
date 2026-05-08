import type { Component, ComponentProps, ValidComponent } from "solid-js";
import { splitProps } from "solid-js";
import { Dynamic } from "solid-js/web";
import type { VariantProps } from "class-variance-authority";
import { cva } from "class-variance-authority";

import { cn } from "../../utils";

export const cardVariants = cva("bg-card text-card-foreground rounded-md", {
  variants: {
    variant: {
      default: "",
      interactive:
        "outline-none cursor-pointer " +
        "motion-safe:transition-[transform,box-shadow] motion-safe:duration-[220ms] motion-safe:ease-[cubic-bezier(0.22,1,0.36,1)] " +
        "hover:[box-shadow:var(--card-hover-light)] hover:motion-safe:-translate-y-px " +
        "focus-visible:[box-shadow:var(--card-hover-light)] focus-visible:motion-safe:-translate-y-px " +
        "dark:hover:[box-shadow:var(--card-hover-dark-underlit)] " +
        "dark:focus-visible:[box-shadow:var(--card-hover-dark-underlit)]",
    },
  },
  defaultVariants: { variant: "default" },
});

export type CardProps<T extends ValidComponent = "div"> = ComponentProps<T> &
  VariantProps<typeof cardVariants> & { as?: T };

export const Card = <T extends ValidComponent = "div">(props: CardProps<T>) => {
  const [, rest] = splitProps(props as CardProps, ["class", "variant", "as"]);
  const tag = (props.as ?? "div") as ValidComponent;

  const hasHref = (props as { href?: unknown }).href != null;
  const isInteractive = props.variant === "interactive";
  const a11yProps =
    isInteractive && !hasHref ? { tabindex: 0, role: "button" } : {};

  return (
    <Dynamic
      component={tag}
      class={cn(cardVariants({ variant: props.variant }), props.class)}
      {...a11yProps}
      {...rest}
    />
  );
};

const CardHeader: Component<ComponentProps<"div">> = (props) => {
  const [local, others] = splitProps(props, ["class"]);
  return <div class={cn("flex flex-col space-y-1.5 p-6", local.class)} {...others} />;
};

const CardTitle: Component<ComponentProps<"h3">> = (props) => {
  const [local, others] = splitProps(props, ["class"]);
  return (
    <h3 class={cn("text-lg font-semibold leading-none tracking-tight", local.class)} {...others} />
  );
};

const CardDescription: Component<ComponentProps<"p">> = (props) => {
  const [local, others] = splitProps(props, ["class"]);
  return <p class={cn("text-sm text-muted-foreground", local.class)} {...others} />;
};

const CardContent: Component<ComponentProps<"div">> = (props) => {
  const [local, others] = splitProps(props, ["class"]);
  return <div class={cn("p-6 pt-0", local.class)} {...others} />;
};

const CardFooter: Component<ComponentProps<"div">> = (props) => {
  const [local, others] = splitProps(props, ["class"]);
  return <div class={cn("flex items-center p-6 pt-0", local.class)} {...others} />;
};

export { CardHeader, CardFooter, CardTitle, CardDescription, CardContent };
