import type { JSX } from "solid-js";
import { For, splitProps } from "solid-js";
import { cn } from "../utils";

export type NavBarItem = {
  label: string;
  href: string;
  external?: boolean;
};

export type NavBarProps = {
  logo: JSX.Element;
  logoHref?: string;
  items?: NavBarItem[];
  actions?: JSX.Element;
  class?: string;
};

export function NavBar(props: NavBarProps): JSX.Element {
  const [local, others] = splitProps(props, ["logo", "logoHref", "items", "actions", "class"]);
  return (
    <nav
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
          {(item) => (
            <li>
              <a
                href={item.href}
                target={item.external ? "_blank" : undefined}
                rel={item.external ? "noopener noreferrer" : undefined}
                class="text-sm font-medium text-foreground whitespace-nowrap transition-all duration-300 cursor-pointer hover:text-primary"
              >
                {item.label}
              </a>
            </li>
          )}
        </For>
      </ul>
      <div class="flex items-center gap-3">{local.actions}</div>
    </nav>
  );
}
