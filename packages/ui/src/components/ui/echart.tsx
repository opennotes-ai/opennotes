import { onMount, onCleanup, createEffect } from "solid-js";
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

export function EChart(props: EChartProps) {
  let containerRef!: HTMLDivElement;
  let chart: echarts.ECharts | undefined;

  onMount(() => {
    chart = echarts.init(containerRef, props.theme ?? "vintage");

    const ro = new ResizeObserver(() => chart?.resize());
    ro.observe(containerRef);

    onCleanup(() => {
      ro.disconnect();
      chart?.dispose();
    });
  });

  createEffect(() => {
    if (chart) {
      chart.setOption(props.option);
    }
  });

  return (
    <div
      ref={containerRef}
      class={props.class}
      style={{ height: props.height ?? "400px", width: "100%" }}
    />
  );
}
