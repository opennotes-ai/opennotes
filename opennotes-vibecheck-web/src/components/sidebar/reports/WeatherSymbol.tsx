import type { JSX } from "solid-js";
import { Switch, Match } from "solid-js";

export type SafetyLevel = "safe" | "mild" | "caution" | "unsafe" | "unknown";

interface TrefoilColors {
  lobe0: string;
  lobe1: string;
  lobe2: string;
  stroke: string;
}

interface SymbolPalette {
  fill: string;
  outline: string;
  trefoilStroke: string;
}

const PALETTE: Record<SafetyLevel, SymbolPalette> = {
  safe:    { fill: "#4ade80", outline: "#bbf7d0", trefoilStroke: "#bbf7d0" },
  mild:    { fill: "#fef9c3", outline: "#fed7aa", trefoilStroke: "#f5a672" },
  caution: { fill: "#facc15", outline: "#8a6608", trefoilStroke: "#8a6608" },
  unsafe:  { fill: "#c0392b", outline: "#fecaca", trefoilStroke: "#fecaca" },
  unknown: { fill: "#e5e7eb", outline: "#6b7280", trefoilStroke: "#6b7280" },
};

export interface WeatherSymbolProps {
  level: SafetyLevel;
  lobeColors: [string, string, string];
  size?: number | string;
  class?: string;
}

const LOBE_PATH = "M0 0 C -6 -10, -16 -22, 0 -32 C 16 -22, 6 -10, 0 0 Z";

function Trefoil(props: { colors: TrefoilColors; scale: number; tx: number; ty: number }): JSX.Element {
  return (
    <g transform={`translate(${props.tx} ${props.ty}) scale(${props.scale})`}>
      <path d={LOBE_PATH} fill={props.colors.lobe0} />
      <g transform="rotate(120)">
        <path d={LOBE_PATH} fill={props.colors.lobe1} />
      </g>
      <g transform="rotate(240)">
        <path d={LOBE_PATH} fill={props.colors.lobe2} />
      </g>
      <path d={LOBE_PATH} fill="none" stroke={props.colors.stroke} stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round" />
      <g transform="rotate(120)">
        <path d={LOBE_PATH} fill="none" stroke={props.colors.stroke} stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round" />
      </g>
      <g transform="rotate(240)">
        <path d={LOBE_PATH} fill="none" stroke={props.colors.stroke} stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round" />
      </g>
    </g>
  );
}

export function WeatherSymbol(props: WeatherSymbolProps): JSX.Element {
  const palette = () => PALETTE[props.level];
  const trefoilColors = (): TrefoilColors => ({
    lobe0: props.lobeColors[0],
    lobe1: props.lobeColors[1],
    lobe2: props.lobeColors[2],
    stroke: palette().trefoilStroke,
  });

  return (
    <Switch>
      <Match when={props.level === "safe"}>
        <svg
          viewBox="0 0 100 100"
          width={props.size ?? 128}
          height={props.size ?? 128}
          aria-hidden="true"
          class={props.class}
          data-testid="weather-symbol-safe"
          stroke-linejoin="round"
          stroke-linecap="round"
        >
          <circle cx="50" cy="50" r="42" fill={palette().fill} />
          <circle
            cx="50" cy="50" r="42"
            fill="none"
            stroke={palette().outline}
            stroke-width="5"
            transform="translate(9 9) scale(0.82)"
          />
          <Trefoil colors={trefoilColors()} scale={0.78} tx={50} ty={50} />
        </svg>
      </Match>
      <Match when={props.level === "mild"}>
        <svg
          viewBox="0 0 100 100"
          width={props.size ?? 128}
          height={props.size ?? 128}
          aria-hidden="true"
          class={props.class}
          data-testid="weather-symbol-mild"
          stroke-linejoin="round"
          stroke-linecap="round"
        >
          <path
            d="M20 8 L80 8 Q92 8 92 20 L92 80 Q92 92 80 92 L20 92 Q8 92 8 80 L8 20 Q8 8 20 8 Z"
            fill={palette().fill}
          />
          <path
            d="M20 8 L80 8 Q92 8 92 20 L92 80 Q92 92 80 92 L20 92 Q8 92 8 80 L8 20 Q8 8 20 8 Z"
            fill="none"
            stroke={palette().outline}
            stroke-width="4"
            transform="translate(8.5 8.5) scale(0.83)"
          />
          <Trefoil colors={trefoilColors()} scale={0.78} tx={50} ty={50} />
        </svg>
      </Match>
      <Match when={props.level === "caution"}>
        <svg
          viewBox="0 0 100 100"
          width={props.size ?? 128}
          height={props.size ?? 128}
          aria-hidden="true"
          class={props.class}
          data-testid="weather-symbol-caution"
          stroke-linejoin="round"
          stroke-linecap="round"
        >
          <path
            d="M55.37 10.73 L92.63 85.27 Q98 96 86 96 L14 96 Q2 96 7.37 85.27 L44.63 10.73 Q50 0 55.37 10.73 Z"
            fill={palette().fill}
          />
          <path
            d="M55.37 10.73 L92.63 85.27 Q98 96 86 96 L14 96 Q2 96 7.37 85.27 L44.63 10.73 Q50 0 55.37 10.73 Z"
            fill="none"
            stroke={palette().outline}
            stroke-width="3.5"
            transform="translate(10.5 13.44) scale(0.79)"
          />
          <Trefoil colors={trefoilColors()} scale={0.65} tx={50} ty={62} />
        </svg>
      </Match>
      <Match when={props.level === "unsafe"}>
        <svg
          viewBox="0 0 100 100"
          width={props.size ?? 128}
          height={props.size ?? 128}
          aria-hidden="true"
          class={props.class}
          data-testid="weather-symbol-unsafe"
          stroke-linejoin="round"
          stroke-linecap="round"
        >
          <path
            d="M38 6 L62 6 Q70 6 75.66 11.66 L88.34 24.34 Q94 30 94 38 L94 62 Q94 70 88.34 75.66 L75.66 88.34 Q70 94 62 94 L38 94 Q30 94 24.34 88.34 L11.66 75.66 Q6 70 6 62 L6 38 Q6 30 11.66 24.34 L24.34 11.66 Q30 6 38 6 Z"
            fill={palette().fill}
          />
          <path
            d="M38 6 L62 6 Q70 6 75.66 11.66 L88.34 24.34 Q94 30 94 38 L94 62 Q94 70 88.34 75.66 L75.66 88.34 Q70 94 62 94 L38 94 Q30 94 24.34 88.34 L11.66 75.66 Q6 70 6 62 L6 38 Q6 30 11.66 24.34 L24.34 11.66 Q30 6 38 6 Z"
            fill="none"
            stroke={palette().outline}
            stroke-width="5"
            transform="translate(8.5 8.5) scale(0.83)"
          />
          <Trefoil colors={trefoilColors()} scale={0.72} tx={50} ty={50} />
        </svg>
      </Match>
      <Match when={props.level === "unknown"}>
        <svg
          viewBox="0 0 100 100"
          width={props.size ?? 128}
          height={props.size ?? 128}
          aria-hidden="true"
          class={props.class}
          data-testid="weather-symbol-unknown"
          stroke-linejoin="round"
          stroke-linecap="round"
        >
          <polygon
            points="50,5 88,50 50,95 12,50"
            fill={palette().fill}
            stroke={palette().outline}
            stroke-width="5"
          />
        </svg>
      </Match>
    </Switch>
  );
}
