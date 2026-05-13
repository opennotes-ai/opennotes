import { onMount, onCleanup, createEffect, createSignal, Show } from "solid-js";
import type { EChartsOption } from "echarts";
import * as echarts from "echarts/core";
import { LineChart, BarChart, ScatterChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DatasetComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  LineChart,
  BarChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DatasetComponent,
  CanvasRenderer,
]);

const CHART_THEME = {
  color: ["#2a9d6e", "#4a7fd4", "#d4874a", "#9a5eb8", "#9a9435", "#3d8b8b", "#c76a6a", "#6b8e5e", "#c4965a", "#5c7fa8"],
};
echarts.registerTheme("vintage", CHART_THEME);

interface EChartProps {
  option: EChartsOption;
  theme?: string;
  height?: string;
  class?: string;
}

function describeSeriesType(option: EChartsOption | undefined): string {
  if (!option) return "unknown";
  const series = (option as { series?: unknown }).series;
  if (!series) return "none";
  if (Array.isArray(series)) {
    const types = series
      .map((s) => (s && typeof s === "object" ? (s as { type?: unknown }).type : undefined))
      .filter((t): t is string => typeof t === "string");
    return types.length ? types.join(",") : "unknown";
  }
  if (typeof series === "object") {
    const t = (series as { type?: unknown }).type;
    return typeof t === "string" ? t : "unknown";
  }
  return "unknown";
}

export function EChart(props: EChartProps) {
  let containerRef!: HTMLDivElement;
  let chart: echarts.ECharts | undefined;
  const [failed, setFailed] = createSignal(false);

  const disposeChart = () => {
    if (chart) {
      try {
        chart.dispose();
      } catch (disposeErr) {
        console.error("[echart] dispose after failure threw:", disposeErr);
      }
      chart = undefined;
    }
  };

  const handleFailure = (phase: string, err: unknown) => {
    const message = err instanceof Error ? err.message : String(err);
    console.error(
      `[echart] ${phase} failed:`,
      message,
      "series:",
      describeSeriesType(props.option),
    );
    disposeChart();
    setFailed(true);
  };

  onMount(() => {
    try {
      chart = echarts.init(containerRef, props.theme ?? "vintage");
    } catch (err) {
      handleFailure("init", err);
      return;
    }

    const ro = new ResizeObserver(() => {
      if (!chart) return;
      try {
        chart.resize();
      } catch (err) {
        handleFailure("resize", err);
      }
    });
    ro.observe(containerRef);

    onCleanup(() => {
      ro.disconnect();
      disposeChart();
    });
  });

  createEffect(() => {
    const option = props.option;
    if (failed() || !chart) return;
    try {
      chart.setOption(option);
    } catch (err) {
      handleFailure("setOption", err);
    }
  });

  return (
    <Show
      when={!failed()}
      fallback={
        <div
          class={props.class}
          style={{ height: props.height ?? "400px", width: "100%" }}
          aria-label="Chart unavailable"
          data-testid="echart-fallback"
        />
      }
    >
      <div
        ref={containerRef}
        class={props.class}
        style={{ height: props.height ?? "400px", width: "100%" }}
      />
    </Show>
  );
}
