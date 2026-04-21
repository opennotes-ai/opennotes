import type { components } from "~/lib/generated-types";
import SafetySection from "./SafetySection";
import ToneDynamicsSection from "./ToneDynamicsSection";
import FactsClaimsSection from "./FactsClaimsSection";
import OpinionsSection from "./OpinionsSection";

type SidebarPayload = components["schemas"]["SidebarPayload"];

export interface SidebarProps {
  payload: SidebarPayload;
}

export default function Sidebar(props: SidebarProps) {
  return (
    <aside
      aria-label="Analysis sidebar"
      data-testid="analysis-sidebar"
      class="flex w-full flex-col gap-4"
    >
      <SafetySection safety={props.payload.safety} />
      <ToneDynamicsSection toneDynamics={props.payload.tone_dynamics} />
      <FactsClaimsSection factsClaims={props.payload.facts_claims} />
      <OpinionsSection opinions={props.payload.opinions_sentiments} />
    </aside>
  );
}
