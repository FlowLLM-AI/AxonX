import { useEffect, useRef, useState } from "react";
import { BarChart, LineChart } from "echarts/charts";
import {
  DataZoomComponent,
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
  DataZoomComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

export function BacktestChart({
  rows,
  series,
  percent = false,
  zoom = false,
  onHover,
  onSelect,
}: {
  rows: ChartRow[];
  series: ChartSeries[];
  percent?: boolean;
  zoom?: boolean;
  onHover?: (date: string) => void;
  onSelect?: (date: string) => void;
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
    const theme = getComputedStyle(host.current);
    const token = (name: string) => theme.getPropertyValue(name).trim();
    const colors = Array.from({ length: 8 }, (_, index) =>
      token(`--chart-${index + 1}`),
    );
    const muted = token("--muted");
    const faint = token("--faint");
    const line = token("--line");
    const surface = token("--surface");
    const ink = token("--ink");
    const chart = init(host.current, undefined, { renderer: "canvas" });
    const format = (value: number, kind?: ChartSeries["format"]) =>
      kind === "percent" || (!kind && percent)
        ? `${(value * 100).toFixed(1)}%`
        : value.toFixed(kind === "precise" ? 4 : kind === "decimal" ? 2 : 3);
    const axisFormat = (axis: 0 | 1) =>
      series.find((item) => (item.axis || 0) === axis)?.format;
    const dualAxis = series.some((item) => item.axis === 1);
    const showZoom = zoom && rows.length > 18;
    const zoomStart = showZoom ? Math.max(0, 100 - 1800 / rows.length) : 0;
    const axisRanges = (start: number, end: number) => {
      const visible = rows.slice(
        Math.floor((start / 100) * (rows.length - 1)),
        Math.ceil((end / 100) * (rows.length - 1)) + 1,
      );
      const extents = ([0, 1] as const).map((axis) => {
        const values = series
          .filter((item) => (item.axis || 0) === axis)
          .flatMap((item) => visible.map((row) => row[item.key]))
          .filter((value) => value != null && value !== "")
          .map(Number)
          .filter(Number.isFinite);
        return {
          positive: Math.max(0, ...values),
          negative: Math.max(0, ...values.map((value) => -value)),
        };
      });
      const positiveShare = Math.min(
        0.85,
        Math.max(
          0.15,
          ...extents.map(({ positive, negative }) =>
            positive + negative ? positive / (positive + negative) : 0,
          ),
        ),
      );
      return extents.map(({ positive, negative }) => {
        const span =
          Math.max(
            positive / positiveShare,
            negative / (1 - positiveShare),
            1e-6,
          ) * 1.08;
        return { min: -(1 - positiveShare) * span, max: positiveShare * span };
      });
    };
    const ranges = dualAxis ? axisRanges(zoomStart, 100) : [];
    chart.setOption({
      animation: false,
      color: colors,
      grid: {
        left: 66,
        right: dualAxis ? 66 : 22,
        top: 68,
        bottom: showZoom ? 76 : 42,
      },
      legend: {
        type: "scroll",
        top: 8,
        textStyle: { color: muted, fontSize: 11 },
      },
      tooltip: {
        trigger: "axis",
        order: "valueDesc",
        backgroundColor: surface,
        borderColor: line,
        textStyle: { color: ink },
        valueFormatter: (value: unknown) => format(Number(value)),
      },
      xAxis: {
        type: "category",
        boundaryGap: series.some((item) => item.type === "bar"),
        data: rows.map((row) => row.date),
        axisLabel: { color: faint, hideOverlap: true },
        axisLine: { lineStyle: { color: line } },
      },
      ...(showZoom
        ? {
            dataZoom: [
              {
                type: "inside",
                start: zoomStart,
                end: 100,
              },
              {
                type: "slider",
                start: zoomStart,
                end: 100,
                bottom: 12,
                height: 20,
                borderColor: line,
                fillerColor: token("--accent-soft"),
                handleStyle: { color: token("--accent") },
                textStyle: { color: faint },
              },
            ],
          }
        : {}),
      yAxis: [
        {
          type: "value",
          ...(dualAxis ? { ...ranges[0], splitNumber: 6 } : {}),
          axisLabel: {
            formatter: (value: number) => format(value, axisFormat(0)),
            color: faint,
          },
          splitLine: { lineStyle: { color: line, opacity: 0.6 } },
        },
        ...(dualAxis
          ? [
              {
                type: "value",
                ...ranges[1],
                splitNumber: 6,
                axisLabel: {
                  formatter: (value: number) => format(value, axisFormat(1)),
                  color: faint,
                },
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
          const raw = row[item.key];
          if (raw == null || raw === "") return null;
          const value = Number(raw);
          return Number.isFinite(value) ? value : null;
        }),
        showSymbol: false,
        connectNulls: false,
        smooth: false,
        barMaxWidth: 24,
        tooltip: {
          valueFormatter: (value: unknown) =>
            format(Number(value), item.format),
        },
        lineStyle: {
          width: item.dashed ? 1.4 : 2,
          type: item.dashed ? "dashed" : "solid",
        },
        emphasis: { focus: "series" },
      })),
    });
    if (dualAxis && showZoom) {
      chart.on("datazoom", () => {
        const state = (chart.getOption() as {
          dataZoom?: { start?: number; end?: number }[];
        }).dataZoom?.[0];
        const next = axisRanges(state?.start ?? 0, state?.end ?? 100);
        chart.setOption({ yAxis: next }, { lazyUpdate: true });
      });
    }
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
  }, [onHover, onSelect, percent, rows, series, theme, zoom]);
  return <div className="backtest-chart" ref={host} />;
}
