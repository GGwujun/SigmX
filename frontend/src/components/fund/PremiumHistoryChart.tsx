import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { graphic } from "echarts/core";
import type { PremiumHistoryItem } from "@/lib/api";

echarts.use([LineChart, GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, CanvasRenderer]);

interface PremiumHistoryChartProps {
  data: PremiumHistoryItem[];
  height?: number;
  showZoom?: boolean;
}

export function PremiumHistoryChart({ data, height = 250, showZoom = false }: PremiumHistoryChartProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current || data.length === 0) return;

    if (!instanceRef.current) {
      instanceRef.current = echarts.init(chartRef.current, undefined, { renderer: "canvas" });
    }
    const chart = instanceRef.current;

    const dates = data.map(d => d.trade_date);
    const premiums = data.map(d => d.premium_rate);

    // Calculate mean for markLine
    const mean = premiums.reduce((a, b) => a + b, 0) / premiums.length;

    const isDark = document.documentElement.classList.contains("dark");
    const textColor = isDark ? "#9ca3af" : "#6b7280";
    const gridColor = isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)";

    chart.setOption({
      tooltip: {
        trigger: "axis",
        formatter: (params: unknown) => {
          const p = (params as Array<{ axisValue: string; data: number }>)[0];
          if (!p) return "";
          const val = p.data;
          const color = val >= 0 ? "#ef4444" : "#22c55e";
          return `<b>${p.axisValue}</b><br/>溢价率: <span style="color:${color};font-weight:bold">${val > 0 ? "+" : ""}${val.toFixed(2)}%</span>`;
        },
      },
      grid: {
        left: 50, right: 20, top: 20, bottom: showZoom ? 60 : 30,
      },
      xAxis: {
        type: "category",
        data: dates,
        axisLabel: { color: textColor, fontSize: 10, rotate: dates.length > 30 ? 45 : 0 },
        axisLine: { lineStyle: { color: gridColor } },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: textColor, fontSize: 10, formatter: "{value}%" },
        splitLine: { lineStyle: { color: gridColor } },
      },
      dataZoom: showZoom ? [{
        type: "slider", start: 0, end: 100, height: 20, bottom: 5,
      }] : undefined,
      series: [{
        type: "line",
        data: premiums,
        smooth: true,
        symbol: "circle",
        symbolSize: 4,
        lineStyle: { width: 2 },
        itemStyle: {
          color: (params: { data: number }) => params.data >= 0 ? "#ef4444" : "#22c55e",
        },
        areaStyle: {
          color: new graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(239,68,68,0.15)" },
            { offset: 0.5, color: "rgba(0,0,0,0)" },
            { offset: 1, color: "rgba(34,197,94,0.15)" },
          ]),
        },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { type: "dashed", color: "#f59e0b", width: 1 },
          data: [{ yAxis: mean, label: { formatter: `均值 ${mean.toFixed(2)}%`, color: "#f59e0b", fontSize: 10 } }],
        },
      }],
    }, true);

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(chartRef.current);

    return () => {
      ro.disconnect();
    };
  }, [data, showZoom]);

  // Cleanup on unmount
  useEffect(() => {
    return () => { instanceRef.current?.dispose(); instanceRef.current = null; };
  }, []);

  if (data.length === 0) {
    return <div className="text-center text-muted-foreground text-sm py-8">暂无历史数据</div>;
  }

  return <div ref={chartRef} style={{ width: "100%", height }} />;
}
