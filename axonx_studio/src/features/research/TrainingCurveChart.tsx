import { useEffect, useRef, useState } from "react";
import { LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import { init, use as registerECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

registerECharts([
  LineChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

export function TrainingCurveChart({
  curve,
}: {
  curve: { x: string[]; y: Record<string, number[]> };
}) {
  const host = useRef<HTMLDivElement>(null);
  const [theme, setTheme] = useState(
    () => document.documentElement.dataset.theme,
  );

  useEffect(() => {
    const observer = new MutationObserver(() =>
      setTheme(document.documentElement.dataset.theme),
    );
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!host.current) return;
    const style = getComputedStyle(host.current);
    const token = (name: string) => style.getPropertyValue(name).trim();
    const series = Object.entries(curve.y).filter(
      ([, values]) => values.length === curve.x.length,
    );
    const zoom = curve.x.length > 80;
    const chart = init(host.current, undefined, { renderer: "canvas" });
    chart.setOption({
      animation: false,
      color: Array.from({ length: 8 }, (_, index) =>
        token(`--chart-${index + 1}`),
      ),
      grid: { left: 68, right: 24, top: 58, bottom: zoom ? 76 : 42 },
      legend: {
        type: "scroll",
        top: 10,
        textStyle: { color: token("--muted"), fontSize: 11 },
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: token("--surface"),
        borderColor: token("--line"),
        textStyle: { color: token("--ink") },
        valueFormatter: (value: unknown) => Number(value).toPrecision(5),
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: curve.x,
        axisLabel: { color: token("--faint"), hideOverlap: true },
        axisLine: { lineStyle: { color: token("--line") } },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: {
          color: token("--faint"),
          formatter: (value: number) => Number(value).toPrecision(3),
        },
        splitLine: { lineStyle: { color: token("--line"), opacity: 0.65 } },
      },
      ...(zoom
        ? {
            dataZoom: [
              { type: "inside", start: 0, end: 100 },
              {
                type: "slider",
                start: 0,
                end: 100,
                bottom: 12,
                height: 20,
                borderColor: token("--line"),
                fillerColor: token("--accent-soft"),
                handleStyle: { color: token("--accent") },
                textStyle: { color: token("--faint") },
              },
            ],
          }
        : {}),
      series: series.map(([name, values]) => ({
        name,
        type: "line",
        data: values.map((value) => (Number.isFinite(value) ? value : null)),
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 2 },
        emphasis: { focus: "series" },
      })),
    });
    const resize = new ResizeObserver(() => chart.resize());
    resize.observe(host.current);
    return () => {
      resize.disconnect();
      chart.dispose();
    };
  }, [curve, theme]);

  return <div className="train-curve-chart" ref={host} />;
}
