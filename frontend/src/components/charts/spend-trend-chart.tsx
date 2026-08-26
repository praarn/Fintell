import type { SpendingTrendPoint } from "@/lib/types";

const WIDTH = 600;
const HEIGHT = 220;
const PADDING = { top: 16, right: 16, bottom: 28, left: 56 };

function formatMoney(value: number): string {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function formatMonth(month: string): string {
  const [year, m] = month.split("-");
  const date = new Date(Number(year), Number(m) - 1, 1);
  return date.toLocaleDateString(undefined, { month: "short" });
}

export function SpendTrendChart({ points }: { points: SpendingTrendPoint[] }) {
  const values = points.map((p) => parseFloat(p.total_spend));
  const max = Math.max(1, ...values);
  const plotWidth = WIDTH - PADDING.left - PADDING.right;
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;

  const stepX = points.length > 1 ? plotWidth / (points.length - 1) : 0;
  const coords = values.map((v, i) => ({
    x: PADDING.left + i * stepX,
    y: PADDING.top + plotHeight - (v / max) * plotHeight,
    value: v,
    month: points[i].month,
  }));

  const linePath = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x} ${c.y}`).join(" ");
  const areaPath =
    coords.length > 0
      ? `${linePath} L ${coords[coords.length - 1].x} ${PADDING.top + plotHeight} ` +
        `L ${coords[0].x} ${PADDING.top + plotHeight} Z`
      : "";

  const yTicks = [0, 0.5, 1].map((f) => Math.round(max * f));

  return (
    <div className="viz-root rounded-xl border p-4" style={{ borderColor: "var(--viz-baseline)" }}>
      <h3 className="mb-2 text-sm font-medium" style={{ color: "var(--viz-text-primary)" }}>
        Monthly spend
      </h3>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" role="img" aria-label="Monthly spend trend">
        {yTicks.map((tick, i) => {
          const y = PADDING.top + plotHeight - (tick / max) * plotHeight;
          return (
            <g key={i}>
              <line
                x1={PADDING.left}
                x2={WIDTH - PADDING.right}
                y1={y}
                y2={y}
                stroke="var(--viz-gridline)"
                strokeWidth={1}
              />
              <text
                x={PADDING.left - 8}
                y={y}
                textAnchor="end"
                dominantBaseline="middle"
                fontSize={11}
                fill="var(--viz-text-muted)"
              >
                {formatMoney(tick)}
              </text>
            </g>
          );
        })}

        {areaPath && <path d={areaPath} fill="var(--viz-series-1-wash)" stroke="none" />}
        {linePath && (
          <path
            d={linePath}
            fill="none"
            stroke="var(--viz-series-1)"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        )}

        {coords.map((c) => (
          <g key={c.month}>
            <circle cx={c.x} cy={c.y} r={4} fill="var(--viz-series-1)" stroke="var(--viz-surface)" strokeWidth={2}>
              <title>
                {c.month}: {formatMoney(c.value)}
              </title>
            </circle>
            <text
              x={c.x}
              y={HEIGHT - PADDING.bottom + 16}
              textAnchor="middle"
              fontSize={11}
              fill="var(--viz-text-muted)"
            >
              {formatMonth(c.month)}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
