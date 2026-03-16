import { onMount, onCleanup, createEffect } from "solid-js";
import type { EChartsOption } from "echarts";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DatasetComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DatasetComponent,
  CanvasRenderer,
]);

interface EChartProps {
  option: EChartsOption;
  height?: string;
  class?: string;
}

export function EChart(props: EChartProps) {
  let containerRef!: HTMLDivElement;
  let chart: echarts.ECharts | undefined;

  onMount(() => {
    chart = echarts.init(containerRef);
    chart.setOption(props.option);

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
