import { onMount, onCleanup, createEffect } from "solid-js";
import type { EChartsOption } from "echarts";
import * as echarts from "echarts/core";
import { LineChart, BarChart } from "echarts/charts";
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
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DatasetComponent,
  CanvasRenderer,
]);

const VINTAGE_THEME = {
  color: ["#d87c7c", "#919e8b", "#d7ab82", "#6e7074", "#61a0a8", "#efa18d", "#787464", "#cc7e63", "#724e58", "#4b565b"],
};
echarts.registerTheme("vintage", VINTAGE_THEME);

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

    const handleResize = () => chart?.resize();
    window.addEventListener("resize", handleResize);

    onCleanup(() => {
      window.removeEventListener("resize", handleResize);
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
