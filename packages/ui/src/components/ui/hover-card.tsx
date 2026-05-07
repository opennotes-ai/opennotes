import type { Component, ValidComponent } from "solid-js"
import { splitProps } from "solid-js"

import * as HoverCardPrimitive from "@kobalte/core/hover-card"
import type { PolymorphicProps } from "@kobalte/core/polymorphic"

import { cn } from "../../utils"

const HoverCardTrigger = HoverCardPrimitive.Trigger

const HoverCard: Component<HoverCardPrimitive.HoverCardRootProps> = (props) => {
  return <HoverCardPrimitive.Root gutter={4} {...props} />
}

type HoverCardContentProps<T extends ValidComponent = "div"> =
  HoverCardPrimitive.HoverCardContentProps<T> & { class?: string | undefined }

const HoverCardContent = <T extends ValidComponent = "div">(
  props: PolymorphicProps<T, HoverCardContentProps<T>>
) => {
  const [local, others] = splitProps(props as HoverCardContentProps, ["class"])
  return (
    <HoverCardPrimitive.Portal>
      <HoverCardPrimitive.Content
        class={cn(
          "z-50 w-72 origin-[var(--kb-popover-content-transform-origin)] rounded-md border bg-popover p-4 text-popover-foreground shadow-md outline-none data-[expanded]:animate-in data-[closed]:animate-out data-[closed]:fade-out-0 data-[expanded]:fade-in-0 data-[closed]:zoom-out-95 data-[expanded]:zoom-in-95",
          local.class
        )}
        {...others}
      />
    </HoverCardPrimitive.Portal>
  )
}

export { HoverCard, HoverCardTrigger, HoverCardContent }
