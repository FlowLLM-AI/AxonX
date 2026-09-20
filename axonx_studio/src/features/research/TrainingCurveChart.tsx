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
import type { TrainingCurveData } from "./types";
import { useTranslation } from "react-i18next";

registerECharts([
  LineChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

export function TrainingCurveChart({ curve }: { curve: TrainingCurveData }) {
  const { t } = useTranslation();
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
    const left = Object.entries(curve.y_left).filter(
      ([, values]) => values.length === curve.x.length,
    );
    const right = Object.entries(curve.y_right).filter(
      ([, values]) => values.length === curve.x.length,
    );
    const dualAxis = right.length > 0;
    const l2Left =
      left.length > 0 && left.every(([name]) => name.endsWith("_l2"));
    const l1Right =
      right.length > 0 && right.every(([name]) => name.endsWith("_l1"));
    const axisRange = (entries: [string, number[]][], start = 0, end = 100) => {
      const from = Math.floor((start / 100) * Math.max(curve.x.length - 1, 0));
      const to = Math.ceil((end / 100) * Math.max(curve.x.length - 1, 0)) + 1;
      let minimum = Infinity;
      let maximum = -Infinity;
      for (const [, points] of entries) {
        for (const value of points.slice(from, to)) {
          if (!Number.isFinite(value)) continue;
          minimum = Math.min(minimum, value);
          maximum = Math.max(maximum, value);
        }
      }
      if (!Number.isFinite(minimum)) return {};
      const padding = Math.max(
        (maximum - minimum) * 0.12,
        Math.abs(maximum) * 0.001,
        1e-6,
      );
      return { min: minimum - padding, max: maximum + padding };
    };
    const axis = (entries: [string, number[]][], side: "left" | "right") => ({
      type: "value",
      position: side,
      scale: true,
      name:
        side === "left"
          ? l2Left
            ? "L2 · MSE"
            : t("trainingCurve.left_axis")
          : l1Right
            ? "L1 · MAE"
            : t("trainingCurve.right_axis"),
      nameTextStyle: { color: token("--muted"), fontSize: 11 },
      ...axisRange(entries),
      axisLabel: {
        color: token("--faint"),
        formatter: (value: number) => Number(value).toPrecision(4),
      },
      splitLine: {
        show: side === "left",
        lineStyle: { color: token("--line"), opacity: 0.65 },
      },
    });
    const displayName = (name: string) =>
      name
        .replace(/^train_/, t("trainingCurve.train"))
        .replace(/^validation_/, t("trainingCurve.validation"))
        .replace(/_l([12])$/, " L$1");
    const zoom = curve.x.length > 80;
    const chart = init(host.current, undefined, { renderer: "canvas" });
    chart.setOption({
      animation: false,
      grid: {
        left: 78,
        right: dualAxis ? 78 : 24,
        top: 66,
        bottom: zoom ? 76 : 42,
      },
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
        valueFormatter: (value: unknown) => Number(value).toPrecision(6),
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: curve.x,
        axisLabel: { color: token("--faint"), hideOverlap: true },
        axisLine: { lineStyle: { color: token("--line") } },
      },
      yAxis: [axis(left, "left"), ...(dualAxis ? [axis(right, "right")] : [])],
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
      series: [
        ...left.map(([name, values], index) => ({
          name,
          values,
          index,
          axis: 0,
        })),
        ...right.map(([name, values], index) => ({
          name,
          values,
          index,
          axis: 1,
        })),
      ].map(({ name, values, index, axis }) => ({
        name: displayName(name),
        type: "line",
        yAxisIndex: axis,
        itemStyle: {
          color: token(
            `--chart-${axis === 0 ? (index % 2 ? 3 : 2) : index % 2 ? 1 : 4}`,
          ),
        },
        data: values.map((value) => (Number.isFinite(value) ? value : null)),
        showSymbol: false,
        connectNulls: false,
        lineStyle: {
          width: 2,
          type: name.startsWith("validation_") ? "dashed" : "solid",
        },
        emphasis: { focus: "series" },
      })),
    });
    if (zoom) {
      chart.on("datazoom", () => {
        const state = (
          chart.getOption() as {
            dataZoom?: { start?: number; end?: number }[];
          }
        ).dataZoom?.[0];
        const start = state?.start ?? 0;
        const end = state?.end ?? 100;
        chart.setOption(
          {
            yAxis: [
              { ...axisRange(left, start, end) },
              ...(dualAxis ? [{ ...axisRange(right, start, end) }] : []),
            ],
          },
          { lazyUpdate: true },
        );
      });
    }
    const resize = new ResizeObserver(() => chart.resize());
    resize.observe(host.current);
    return () => {
      resize.disconnect();
      chart.dispose();
    };
  }, [curve, theme, t]);

  return <div className="train-curve-chart" ref={host} />;
}
