import type { JSX } from "solid-js";
import { getAssetUrl } from "../utils/asset-url";

export interface LogoProps {
  class?: string;
  alt?: string;
}

export function Logo(props: LogoProps): JSX.Element {
  return (
    <img
      src={getAssetUrl("opennotes-logo.svg")}
      alt={props.alt ?? "Open Notes"}
      class={props.class}
    />
  );
}
