import { useEffect, useRef } from "react";
import { echarts } from "@/lib/echarts";
import { useDarkMode } from "@/hooks/useDarkMode";
import type { EChartsOption } from "echarts";
import { cn } from "@/lib/utils";

/** Thin echarts wrapper: init once, update option on change, resize + dispose. */
export function Chart({
  option,
  height = 220,
  className,
  group,
}: {
  option: EChartsOption;
  height?: number;
  className?: string;
  group?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null);
  const { dark } = useDarkMode();

  useEffect(() => {
    if (!ref.current) return;
    if (!chartRef.current) {
      chartRef.current = echarts.init(ref.current, undefined, { renderer: "canvas" });
      if (group) chartRef.current.group = group;
    }
    chartRef.current.setOption(option, { notMerge: false });
  }, [option, group]);

  useEffect(() => {
    const el = ref.current;
    const chart = chartRef.current;
    if (!el || !chart) return;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, []);

  useEffect(() => {
    chartRef.current?.resize();
  }, [dark]);

  useEffect(() => {
    return () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  return <div ref={ref} className={cn("w-full", className)} style={{ height }} />;
}
