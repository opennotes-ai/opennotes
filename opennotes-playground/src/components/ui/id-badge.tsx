import { Tooltip } from "@kobalte/core/tooltip";
import { Badge, type BadgeVariant } from "~/components/ui/badge";
import { formatIdBadgeLabel, formatIdBadgeTooltip } from "~/lib/format";

type IdBadgeProps = {
  idValue: string | null | undefined;
  variant?: BadgeVariant;
  class?: string;
};

export default function IdBadge(props: IdBadgeProps) {
  return (
    <Tooltip>
      <Tooltip.Trigger as="span" class="inline-flex align-middle">
        <Badge variant={props.variant ?? "muted"} class={`text-[0.8125rem] ${props.class ?? ""}`}>
          {formatIdBadgeLabel(props.idValue)}
        </Badge>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content class="z-50 rounded-md border border-border bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md">
          <span class="font-mono whitespace-pre-line leading-tight">
            {formatIdBadgeTooltip(props.idValue)}
          </span>
          <Tooltip.Arrow class="fill-popover" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip>
  );
}
