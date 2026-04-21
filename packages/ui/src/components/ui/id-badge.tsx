import { Tooltip, TooltipTrigger, TooltipContent } from "./tooltip";
import { Badge, type BadgeVariant } from "./badge";
import { formatIdBadgeLabel, formatIdBadgeTooltip } from "../../utils";

type IdBadgeProps = {
  idValue: string | null | undefined;
  name?: string | null;
  variant?: BadgeVariant;
  class?: string;
};

export default function IdBadge(props: IdBadgeProps) {
  return (
    <Tooltip>
      <TooltipTrigger as="span" class="inline-flex align-middle">
        <Badge variant={props.variant ?? "muted"} class={`text-[0.8125rem] ${props.class ?? ""}`}>
          {formatIdBadgeLabel(props.idValue, props.name)}
        </Badge>
      </TooltipTrigger>
      <TooltipContent class="z-50 rounded-md border border-border bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md">
        <span class="font-mono whitespace-pre-line leading-tight">
          {formatIdBadgeTooltip(props.idValue, props.name)}
        </span>
      </TooltipContent>
    </Tooltip>
  );
}
