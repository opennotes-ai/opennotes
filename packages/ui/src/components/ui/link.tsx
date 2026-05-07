import type { JSX } from "solid-js";
import { Show, splitProps } from "solid-js";
import type { VariantProps } from "class-variance-authority";
import { cva } from "class-variance-authority";
import { cn } from "../../utils";

export const linkVariants = cva(
  "inline-flex items-center gap-1 rounded-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none",
  {
    variants: {
      variant: {
        default: "text-primary underline-offset-4 hover:underline",
        muted:
          "underline underline-offset-4 hover:text-foreground text-muted-foreground",
      },
      size: {
        default: "text-sm",
        sm: "text-xs",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

type LinkVariantProps = VariantProps<typeof linkVariants>;

type SharedLinkProps = LinkVariantProps & {
  class?: string;
  children?: JSX.Element;
};

export type AnchorLinkProps = SharedLinkProps &
  Omit<JSX.AnchorHTMLAttributes<HTMLAnchorElement>, "class" | "children"> & {
    href: string;
  };

export type ButtonLinkProps = SharedLinkProps &
  Omit<JSX.ButtonHTMLAttributes<HTMLButtonElement>, "class" | "children"> & {
    href?: undefined;
  };

export type LinkProps = AnchorLinkProps | ButtonLinkProps;

export const Link = (props: LinkProps) => {
  const [variantProps, rest] = splitProps(props as SharedLinkProps & { href?: string }, [
    "class",
    "variant",
    "size",
    "children",
  ]);

  const classes = () =>
    cn(
      linkVariants({
        variant: variantProps.variant,
        size: variantProps.size,
      }),
      variantProps.class,
    );

  return (
    <Show
      when={(rest as { href?: string }).href !== undefined}
      fallback={
        <button
          type="button"
          data-slot="link"
          {...(rest as JSX.ButtonHTMLAttributes<HTMLButtonElement>)}
          class={classes()}
        >
          {variantProps.children}
        </button>
      }
    >
      <a
        data-slot="link"
        {...(rest as JSX.AnchorHTMLAttributes<HTMLAnchorElement>)}
        class={classes()}
      >
        {variantProps.children}
      </a>
    </Show>
  );
};
