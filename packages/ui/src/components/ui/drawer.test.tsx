import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import {
  Drawer,
  DrawerTrigger,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerDescription,
  DrawerFooter,
  DrawerClose,
} from "./drawer"

const drawerSource = readFileSync(resolve("src/components/ui/drawer.tsx"), "utf8")

describe("<Drawer /> source contract", () => {
  it("builds on @kobalte/core/dialog (reuses Sheet's Kobalte primitive)", () => {
    expect(drawerSource).toContain("@kobalte/core/dialog")
  })

  it("DrawerContent is bottom-anchored (inset-x-0 bottom-0)", () => {
    expect(drawerSource).toContain("inset-x-0")
    expect(drawerSource).toContain("bottom-0")
  })

  it("content panel has border-t for top edge separation", () => {
    expect(drawerSource).toContain("border-t")
  })

  it("has a drag handle visual indicator (data-drag-handle or .drag-handle class)", () => {
    expect(drawerSource).toMatch(/drag-handle|drag_handle/)
  })

  it("uses slide-in-from-bottom and slide-out-to-bottom transition classes", () => {
    expect(drawerSource).toContain("slide-in-from-bottom")
    expect(drawerSource).toContain("slide-out-to-bottom")
  })

  it("includes data-[expanded] animate-in and data-[closed] animate-out transitions", () => {
    expect(drawerSource).toContain("data-[expanded]")
    expect(drawerSource).toContain("data-[closed]")
    expect(drawerSource).toContain("animate-in")
    expect(drawerSource).toContain("animate-out")
  })

  it("renders DialogPrimitive.Overlay for the backdrop", () => {
    expect(drawerSource).toContain("DialogPrimitive.Overlay")
  })

  it("wraps content in DialogPrimitive.Portal", () => {
    expect(drawerSource).toContain("DialogPrimitive.Portal")
  })

  it("DrawerClose renders DialogPrimitive.CloseButton", () => {
    expect(drawerSource).toContain("DialogPrimitive.CloseButton")
  })

  it("DrawerContent embeds a close button with sr-only label", () => {
    expect(drawerSource).toContain("sr-only")
  })

  it("uses splitProps to extract class so arbitrary props forward to the primitive", () => {
    expect(drawerSource).toContain("splitProps")
    expect(drawerSource).toContain("...others")
  })

  it("merges caller class via cn() helper", () => {
    expect(drawerSource).toContain("cn(")
    expect(drawerSource).toMatch(/cn\([^)]*\.class/)
  })

  it("content panel has bg-background for themed surface", () => {
    expect(drawerSource).toContain("bg-background")
  })

  it("DrawerTitle uses text-lg font-semibold", () => {
    expect(drawerSource).toContain("text-lg")
    expect(drawerSource).toContain("font-semibold")
  })

  it("DrawerDescription uses text-sm text-muted-foreground", () => {
    expect(drawerSource).toContain("text-sm")
    expect(drawerSource).toContain("text-muted-foreground")
  })

  it("DrawerHeader has flex flex-col for vertical stacking", () => {
    expect(drawerSource).toContain("flex flex-col")
  })

  it("DrawerHeader text is centered (text-center) matching mobile bottom-sheet conventions", () => {
    expect(drawerSource).toContain("text-center")
  })

  it("DrawerFooter has flex flex-col-reverse or flex-col for stacked button layout", () => {
    expect(drawerSource).toMatch(/flex-col-reverse|flex-col/)
  })

  it("uses tailwind tokens only (no inline hex colors)", () => {
    expect(drawerSource).not.toMatch(/#[0-9a-fA-F]{3,8}/)
  })

  it("tags DrawerContent with data-slot=\"drawer-content\" for design-system attribution", () => {
    expect(drawerSource).toContain('data-slot="drawer-content"')
  })
})

describe("<Drawer /> module surface", () => {
  it("exports Drawer as a function component", () => {
    expect(typeof Drawer).toBe("function")
  })

  it("exports DrawerTrigger as a function component", () => {
    expect(typeof DrawerTrigger).toBe("function")
  })

  it("exports DrawerContent as a function component", () => {
    expect(typeof DrawerContent).toBe("function")
  })

  it("exports DrawerHeader as a function component", () => {
    expect(typeof DrawerHeader).toBe("function")
  })

  it("exports DrawerTitle as a function component", () => {
    expect(typeof DrawerTitle).toBe("function")
  })

  it("exports DrawerDescription as a function component", () => {
    expect(typeof DrawerDescription).toBe("function")
  })

  it("exports DrawerFooter as a function component", () => {
    expect(typeof DrawerFooter).toBe("function")
  })

  it("exports DrawerClose as a function component", () => {
    expect(typeof DrawerClose).toBe("function")
  })
})
