import { useEffect, useRef } from "react";
import { BarChart, LineChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import { init, use as registerECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import type { ChartRow, ChartSeries } from "./types";

registerECharts([
  LineChart,
  BarChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

const colors = [
  "#2f8f68",
  "#3975d5",
  "#9061c2",
  "#d28235",
  "#d34f6f",
  "#15999c",
  "#617083",
  "#b49b32",
];

export function BacktestChart({
  rows,
  series,
  percent = false,
  onHover,
  onSelect,
}: {
  rows: ChartRow[];
  series: ChartSeries[];
  percent?: boolean;
  onHover?: (date: string) => void;
  onSelect?: (date: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!host.current) return;
    const chart = init(host.current, undefined, { renderer: "canvas" });
    const format = (value: number) =>
      percent ? `${(value * 100).toFixed(1)}%` : value.toFixed(3);
    chart.setOption({
      animation: false,
      color: colors,
      grid: {
        left: 66,
        right: series.some((item) => item.axis === 1) ? 66 : 22,
        top: 68,
        bottom: 42,
      },
      legend: {
        type: "scroll",
        top: 8,
        textStyle: { color: "#718078", fontSize: 11 },
      },
      tooltip: {
        trigger: "axis",
        order: "valueDesc",
        valueFormatter: (value: unknown) => format(Number(value)),
      },
      xAxis: {
        type: "category",
        boundaryGap: series.some((item) => item.type === "bar"),
        data: rows.map((row) => row.date),
        axisLabel: { color: "#849089", hideOverlap: true },
        axisLine: { lineStyle: { color: "#dfe5e1" } },
      },
      yAxis: [
        {
          type: "value",
          axisLabel: { formatter: format, color: "#849089" },
          splitLine: { lineStyle: { color: "#edf1ef" } },
        },
        ...(series.some((item) => item.axis === 1)
          ? [
              {
                type: "value",
                axisLabel: { formatter: format, color: "#849089" },
                splitLine: { show: false },
              },
            ]
          : []),
      ],
      series: series.map((item) => ({
        name: item.label,
        type: item.type || "line",
        yAxisIndex: item.axis || 0,
        data: rows.map((row) => {
          const value = Number(row[item.key]);
          return Number.isFinite(value) ? value : null;
        }),
        showSymbol: false,
        connectNulls: false,
        smooth: false,
        barMaxWidth: 24,
        lineStyle: {
          width: item.dashed ? 1.4 : 2,
          type: item.dashed ? "dashed" : "solid",
        },
        emphasis: { focus: "series" },
      })),
    });
    const dateAt = (params: unknown) =>
      rows[(params as { dataIndex: number }).dataIndex]?.date;
    chart.on("mouseover", (params) => onHover?.(dateAt(params)));
    chart.on("click", (params) => onSelect?.(dateAt(params)));
    const resize = new ResizeObserver(() => chart.resize());
    resize.observe(host.current);
    return () => {
      resize.disconnect();
      chart.dispose();
    };
  }, [onHover, onSelect, percent, rows, series]);
  return <div className="backtest-chart" ref={host} />;
}
