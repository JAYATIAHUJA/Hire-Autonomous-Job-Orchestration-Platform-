export default function ProgressRing({ value, done }: { value: number; done?: boolean }) {
  const r = 22
  const c = 2 * Math.PI * r
  return (
    <svg className="analysis-ring" viewBox="0 0 54 54" aria-hidden="true">
      <circle cx="27" cy="27" r={r} fill="none" stroke="var(--surface-3)" strokeWidth="5" />
      <circle
        cx="27"
        cy="27"
        r={r}
        fill="none"
        stroke={done ? 'var(--good)' : 'var(--accent)'}
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - value / 100)}
        transform="rotate(-90 27 27)"
        style={{ transition: 'stroke-dashoffset 0.5s ease' }}
      />
      <text x="27" y="31" textAnchor="middle" fontSize="12" fontWeight="700" fill="var(--ink)">
        {done ? '✓' : `${value}%`}
      </text>
    </svg>
  )
}
