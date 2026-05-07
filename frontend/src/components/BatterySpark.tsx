interface Props {
  values: number[]; // battery_pct readings, 0–100
  color: "green" | "yellow" | "red" | "grey";
}

const COLOR_MAP = {
  green: "#16a34a",
  yellow: "#ca8a04",
  red: "#dc2626",
  grey: "#6b7280",
};

const W = 180;
const H = 28;

export function BatterySpark({ values, color }: Props) {
  if (values.length < 2) return null;

  const stroke = COLOR_MAP[color];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1; // avoid div/0 when all values equal

  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * W;
      const y = H - ((v - min) / range) * H;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width={W}
      height={H}
      aria-hidden
      className="block w-full"
    >
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity={0.85}
      />
    </svg>
  );
}
