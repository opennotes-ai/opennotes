import type { JSX } from "solid-js";
import { For, splitProps } from "solid-js";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { cn } from "../utils";

export type NavBarItem = {
  label: string;
  href: string;
  external?: boolean;
};

export type NavBarDropdownItem = {
  label: string;
  items: NavBarItem[];
};

export type NavBarEntry = NavBarItem | NavBarDropdownItem;

export type NavBarProps = {
  logo: JSX.Element;
  logoHref?: string;
  items?: NavBarEntry[];
  actions?: JSX.Element;
  class?: string;
};

function isDropdown(entry: NavBarEntry): entry is NavBarDropdownItem {
  return "items" in entry;
}

const linkClass =
  "text-sm font-medium text-foreground whitespace-nowrap transition-all duration-300 cursor-pointer hover:text-primary";

export function NavBar(props: NavBarProps): JSX.Element {
  const [local, others] = splitProps(props, ["logo", "logoHref", "items", "actions", "class"]);
  return (
    <nav
      aria-label="Main navigation"
      class={cn(
        "flex h-16 items-center gap-6 border-b border-border bg-background/80 backdrop-blur-lg px-4 sm:px-6 lg:px-8",
        local.class,
      )}
      {...others}
    >
      <a href={local.logoHref ?? "/"} class="flex items-center">
        {local.logo}
      </a>
      <div class="flex-1" />
      <ul class="hidden sm:flex items-center gap-5">
        <For each={local.items ?? []}>
          {(entry) => (
            <li>
              {isDropdown(entry) ? (
                <DropdownMenu gutter={8}>
                  <DropdownMenuTrigger
                    class={cn(linkClass, "flex items-center gap-1 outline-none")}
                  >
                    {entry.label}
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      class="size-3 opacity-60"
                    >
                      <path d="M6 9l6 6 6-6" />
                    </svg>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent class="z-50 min-w-[10rem] origin-[var(--kb-menu-content-transform-origin)] overflow-hidden rounded-md border border-border bg-background/95 backdrop-blur-lg p-1 shadow-md animate-in data-[expanded]:animate-content-show data-[closed]:animate-content-hide">
                    <For each={entry.items}>
                      {(item) => (
                        <DropdownMenuItem
                          class="gap-0 p-0 rounded-sm transition-none outline-none focus:bg-accent data-[highlighted]:bg-accent"
                          onSelect={() => {
                            window.open(
                              item.href,
                              item.external ? "_blank" : "_self",
                              item.external ? "noopener,noreferrer" : "",
                            );
                          }}
                        >
                          <a
                            href={item.href}
                            target={item.external ? "_blank" : undefined}
                            rel={item.external ? "noopener noreferrer" : undefined}
                            class="flex w-full px-3 py-2 text-sm text-foreground transition-colors hover:text-primary"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {item.label}
                          </a>
                        </DropdownMenuItem>
                      )}
                    </For>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <a
                  href={entry.href}
                  target={entry.external ? "_blank" : undefined}
                  rel={entry.external ? "noopener noreferrer" : undefined}
                  class={linkClass}
                >
                  {entry.label}
                </a>
              )}
            </li>
          )}
        </For>
      </ul>
      <div class="flex items-center gap-3">{local.actions}</div>
    </nav>
  );
}
