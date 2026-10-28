import { BarChart, LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import { init, use as registerECharts, type EChartsType } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef, useState } from "react";

registerECharts([
  BarChart,
  LineChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);
export type ChartRenderer = (
  chart: EChartsType,
  token: (name: string) => string,
) => void;
/** One chart instance per mounted surface; observers and events share its lifetime. */
export function useChart(render: ChartRenderer) {
  const host = useRef<HTMLDivElement>(null);
  const instance = useRef<EChartsType | null>(null);
  const [theme, setTheme] = useState(
    () => document.documentElement.dataset.theme,
  );
  useEffect(() => {
    const element = host.current!;
    const chart = init(element, undefined, { renderer: "canvas" });
    instance.current = chart;
    const resize = new ResizeObserver(() => chart.resize());
    const appearance = new MutationObserver(() =>
      setTheme(document.documentElement.dataset.theme),
    );
    resize.observe(element);
    appearance.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => {
      resize.disconnect();
      appearance.disconnect();
      chart.dispose();
      instance.current = null;
    };
  }, []);
  useEffect(() => {
    const style = getComputedStyle(host.current!);
    render(instance.current!, (name) => style.getPropertyValue(name).trim());
  }, [render, theme]);
  return host;
}
