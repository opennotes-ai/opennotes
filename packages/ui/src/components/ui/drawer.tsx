import type { Component, ComponentProps, JSX, ValidComponent } from "solid-js"
import { splitProps } from "solid-js"

import * as DialogPrimitive from "@kobalte/core/dialog"
import type { PolymorphicProps } from "@kobalte/core/polymorphic"

import { cn } from "../../utils"

const Drawer = DialogPrimitive.Root
const DrawerTrigger = DialogPrimitive.Trigger
const DrawerClose = DialogPrimitive.CloseButton

type DrawerOverlayProps<T extends ValidComponent = "div"> = DialogPrimitive.DialogOverlayProps<T> & {
  class?: string | undefined
}

const DrawerOverlay = <T extends ValidComponent = "div">(
  props: PolymorphicProps<T, DrawerOverlayProps<T>>
) => {
  const [local, others] = splitProps(props as DrawerOverlayProps, ["class"])
  return (
    <DialogPrimitive.Overlay
      class={cn(
        "fixed inset-0 z-50 bg-black/80 data-[expanded]:animate-in data-[closed]:animate-out data-[closed]:fade-out-0 data-[expanded]:fade-in-0",
        local.class
      )}
      {...others}
    />
  )
}

type DrawerContentProps<T extends ValidComponent = "div"> = DialogPrimitive.DialogContentProps<T> & {
  class?: string | undefined
  children?: JSX.Element
}

const DrawerContent = <T extends ValidComponent = "div">(
  props: PolymorphicProps<T, DrawerContentProps<T>>
) => {
  const [local, others] = splitProps(props as DrawerContentProps, ["class", "children"])
  return (
    <DialogPrimitive.Portal>
      <DrawerOverlay />
      <DialogPrimitive.Content
        data-slot="drawer-content"
        class={cn(
          "fixed inset-x-0 bottom-0 z-50 flex flex-col gap-4 bg-background p-6 shadow-lg border-t data-[expanded]:animate-in data-[closed]:animate-out data-[closed]:slide-out-to-bottom data-[expanded]:slide-in-from-bottom duration-300",
          local.class
        )}
        {...others}
      >
        <div class="mx-auto mt-0 mb-2 flex items-center justify-center">
          <div class="drag-handle h-1.5 w-12 rounded-full bg-muted" />
        </div>
        {local.children}
        <DialogPrimitive.CloseButton class="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="size-4"
          >
            <path d="M18 6l-12 12" />
            <path d="M6 6l12 12" />
          </svg>
          <span class="sr-only">Close</span>
        </DialogPrimitive.CloseButton>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}

const DrawerHeader: Component<ComponentProps<"div">> = (props) => {
  const [local, others] = splitProps(props, ["class"])
  return (
    <div
      class={cn("flex flex-col space-y-1.5 text-center", local.class)}
      {...others}
    />
  )
}

const DrawerFooter: Component<ComponentProps<"div">> = (props) => {
  const [local, others] = splitProps(props, ["class"])
  return (
    <div
      class={cn("flex flex-col-reverse gap-2 mt-auto", local.class)}
      {...others}
    />
  )
}

type DrawerTitleProps<T extends ValidComponent = "h2"> = DialogPrimitive.DialogTitleProps<T> & {
  class?: string | undefined
}

const DrawerTitle = <T extends ValidComponent = "h2">(
  props: PolymorphicProps<T, DrawerTitleProps<T>>
) => {
  const [local, others] = splitProps(props as DrawerTitleProps, ["class"])
  return (
    <DialogPrimitive.Title
      class={cn("text-lg font-semibold leading-none tracking-tight", local.class)}
      {...others}
    />
  )
}

type DrawerDescriptionProps<T extends ValidComponent = "p"> =
  DialogPrimitive.DialogDescriptionProps<T> & { class?: string | undefined }

const DrawerDescription = <T extends ValidComponent = "p">(
  props: PolymorphicProps<T, DrawerDescriptionProps<T>>
) => {
  const [local, others] = splitProps(props as DrawerDescriptionProps, ["class"])
  return (
    <DialogPrimitive.Description
      class={cn("text-sm text-muted-foreground", local.class)}
      {...others}
    />
  )
}

export {
  Drawer,
  DrawerTrigger,
  DrawerClose,
  DrawerContent,
  DrawerHeader,
  DrawerFooter,
  DrawerTitle,
  DrawerDescription,
}
