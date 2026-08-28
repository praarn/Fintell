interface BarDatum {
  label: string;
  value: number;
}

function formatMoney(value: number): string {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export function RankedBarChart({ title, data }: { title: string; data: BarDatum[] }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  const rowHeight = 28;
  const barMax = 24; // spec: bars capped at 24px thick
  const labelWidth = 140;
  const chartWidth = 420;
  const height = data.length * rowHeight + 8;

  if (data.length === 0) {
    return (
      <div className="viz-root card card-pad text-sm" style={{ color: "var(--viz-text-secondary)" }}>
        <h3 className="mb-2 font-medium" style={{ color: "var(--viz-text-primary)" }}>
          {title}
        </h3>
        No data yet.
      </div>
    );
  }

  return (
    <div className="viz-root card card-pad">
      <h3 className="mb-2 text-sm font-medium" style={{ color: "var(--viz-text-primary)" }}>
        {title}
      </h3>
      <svg
        viewBox={`0 0 ${labelWidth + chartWidth + 70} ${height}`}
        className="w-full"
        role="img"
        aria-label={title}
      >
        {data.map((d, i) => {
          const y = i * rowHeight + rowHeight / 2;
          const barWidth = (d.value / max) * chartWidth;
          return (
            <g key={d.label}>
              <text
                x={labelWidth - 8}
                y={y}
                textAnchor="end"
                dominantBaseline="middle"
                fontSize={12}
                fill="var(--viz-text-secondary)"
              >
                {d.label.length > 22 ? `${d.label.slice(0, 21)}…` : d.label}
              </text>
              <rect
                x={labelWidth}
                y={y - barMax / 2}
                width={Math.max(barWidth, 2)}
                height={barMax}
                rx={4}
                fill="var(--viz-series-1)"
              >
                <title>
                  {d.label}: {formatMoney(d.value)}
                </title>
              </rect>
              <text
                x={labelWidth + barWidth + 8}
                y={y}
                dominantBaseline="middle"
                fontSize={12}
                fill="var(--viz-text-primary)"
              >
                {formatMoney(d.value)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
