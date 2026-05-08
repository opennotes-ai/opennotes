import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "./dialog"

const dialogSource = readFileSync(resolve("src/components/ui/dialog.tsx"), "utf8")

describe("<Dialog /> source contract", () => {
  it("builds on @kobalte/core/dialog (not a custom impl)", () => {
    expect(dialogSource).toContain("@kobalte/core/dialog")
  })

  it("wraps content in DialogPrimitive.Portal so it mounts outside the DOM tree", () => {
    expect(dialogSource).toContain("DialogPrimitive.Portal")
  })

  it("renders DialogPrimitive.Overlay for the backdrop", () => {
    expect(dialogSource).toContain("DialogPrimitive.Overlay")
  })

  it("DialogContent uses sm:max-w-[425px] for the centered modal width", () => {
    expect(dialogSource).toContain("sm:max-w-[425px]")
  })

  it("uses fixed inset-0 z-50 for full-screen overlay positioning", () => {
    expect(dialogSource).toContain("fixed inset-0 z-50")
  })

  it("backdrop has bg-black/80 semi-transparent scrim", () => {
    expect(dialogSource).toContain("bg-black/80")
  })

  it("content panel has bg-background for themed surface", () => {
    expect(dialogSource).toContain("bg-background")
  })

  it("includes data-[expanded] animate-in and data-[closed] animate-out transitions", () => {
    expect(dialogSource).toContain("data-[expanded]")
    expect(dialogSource).toContain("data-[closed]")
    expect(dialogSource).toContain("animate-in")
    expect(dialogSource).toContain("animate-out")
  })

  it("DialogClose renders DialogPrimitive.CloseButton (Esc / click-outside close comes from Kobalte)", () => {
    expect(dialogSource).toContain("DialogPrimitive.CloseButton")
  })

  it("DialogContent embeds a close button with sr-only label for screen readers", () => {
    expect(dialogSource).toContain("sr-only")
  })

  it("uses splitProps to extract class so arbitrary props forward to the primitive", () => {
    expect(dialogSource).toContain("splitProps")
    expect(dialogSource).toContain("...others")
  })

  it("merges caller class via cn() helper", () => {
    expect(dialogSource).toContain("cn(")
    expect(dialogSource).toMatch(/cn\([^)]*\.class/)
  })

  it("DialogTitle uses text-lg font-semibold for visual hierarchy", () => {
    expect(dialogSource).toContain("text-lg")
    expect(dialogSource).toContain("font-semibold")
  })

  it("DialogDescription uses text-sm text-muted-foreground", () => {
    expect(dialogSource).toContain("text-sm")
    expect(dialogSource).toContain("text-muted-foreground")
  })

  it("DialogHeader has flex flex-col space-y-1.5", () => {
    expect(dialogSource).toContain("flex flex-col")
    expect(dialogSource).toContain("space-y-1.5")
  })

  it("DialogFooter has sm:flex-row sm:justify-end for button alignment", () => {
    expect(dialogSource).toContain("sm:flex-row")
    expect(dialogSource).toContain("sm:justify-end")
  })

  it("uses tailwind tokens only (no inline hex colors)", () => {
    expect(dialogSource).not.toMatch(/#[0-9a-fA-F]{3,8}/)
  })

  it("tags DialogContent with data-slot=\"dialog-content\" for design-system attribution", () => {
    expect(dialogSource).toContain('data-slot="dialog-content"')
  })
})

describe("<Dialog /> module surface", () => {
  it("exports Dialog as a function component", () => {
    expect(typeof Dialog).toBe("function")
  })

  it("exports DialogTrigger as a function component", () => {
    expect(typeof DialogTrigger).toBe("function")
  })

  it("exports DialogContent as a function component", () => {
    expect(typeof DialogContent).toBe("function")
  })

  it("exports DialogHeader as a function component", () => {
    expect(typeof DialogHeader).toBe("function")
  })

  it("exports DialogTitle as a function component", () => {
    expect(typeof DialogTitle).toBe("function")
  })

  it("exports DialogDescription as a function component", () => {
    expect(typeof DialogDescription).toBe("function")
  })

  it("exports DialogFooter as a function component", () => {
    expect(typeof DialogFooter).toBe("function")
  })

  it("exports DialogClose as a function component", () => {
    expect(typeof DialogClose).toBe("function")
  })
})
