// A two-stage flow (Sankey through one hub): where jobs come from -> all live jobs ->
// what happened to them for this candidate. Band widths are the real counts, with a
// floor so a small number stays visible.

export type FlowNode = { label: string; value: number; color: string }

type Props = {
  left: FlowNode[]
  hubLabel: string
  right: FlowNode[]
  height?: number
}

const W = 640
const BAND_MAX = 150 // px of total band thickness at the hub
const MIN = 3

function stack(nodes: FlowNode[], total: number, top: number, gap: number) {
  let y = top
  return nodes.map((n) => {
    const h = Math.max(MIN, total ? (n.value / total) * BAND_MAX : MIN)
    const out = { ...n, y, h }
    y += h + gap
    return out
  })
}

export default function FlowChart({ left, hubLabel, right, height = 260 }: Props) {
  const total = Math.max(1, left.reduce((s, n) => s + n.value, 0))
  const rightTotal = Math.max(1, right.reduce((s, n) => s + n.value, 0))
  const gapL = Math.max(8, (height - 20 - BAND_MAX) / Math.max(1, left.length - 1))
  const gapR = Math.max(8, (height - 20 - BAND_MAX) / Math.max(1, right.length - 1))
  const L = stack(left, total, 10, gapL)
  const R = stack(right, rightTotal, 10, gapR)
  // Room under the lowest node for its two label lines.
  const bottom = Math.max(...[...L, ...R].map((n) => n.y + n.h)) + 30
  const viewH = Math.max(height, bottom)

  const hubX = W / 2
  const hubTop = height / 2 - BAND_MAX / 2
  const xL = 120 // where left labels end
  const xR = W - 120

  // Hub offsets, so bands arrive stacked and leave stacked.
  let inY = hubTop
  let outY = hubTop

  const band = (x1: number, y1: number, h1: number, x2: number, y2: number, h2: number) => {
    const c = (x1 + x2) / 2
    return `M${x1},${y1} C${c},${y1} ${c},${y2} ${x2},${y2} L${x2},${y2 + h2} C${c},${y2 + h2} ${c},${y1 + h1} ${x1},${y1 + h1} Z`
  }

  return (
    <svg viewBox={`0 0 ${W} ${viewH}`} className="flow-chart" role="img" aria-label={`${hubLabel}: ${left.map((n) => `${n.label} ${n.value}`).join(', ')}; ${right.map((n) => `${n.label} ${n.value}`).join(', ')}`}>
      {L.map((n) => {
        const h2 = Math.max(MIN * 0.6, (n.value / total) * BAND_MAX)
        const d = band(xL, n.y, n.h, hubX - 6, inY, h2)
        inY += h2
        return <path key={`l-${n.label}`} d={d} fill={n.color} opacity={0.75} />
      })}
      {R.map((n) => {
        const h1 = Math.max(MIN * 0.6, (n.value / rightTotal) * BAND_MAX)
        const d = band(hubX + 6, outY, h1, xR, n.y, n.h)
        outY += h1
        return <path key={`r-${n.label}`} d={d} fill={n.color} opacity={0.75} />
      })}
      <rect x={hubX - 6} y={hubTop - 4} width={12} height={BAND_MAX + 8} rx={6} fill="#1c1c1f" />

      {L.map((n) => (
        <g key={`lt-${n.label}`}>
          <rect x={xL - 4} y={n.y} width={3} height={n.h} rx={1.5} fill="#c9c9c2" />
          <text x={xL - 12} y={n.y + n.h / 2 - 3} textAnchor="end" className="flow-label">
            {n.label}
          </text>
          <text x={xL - 12} y={n.y + n.h / 2 + 12} textAnchor="end" className="flow-value">
            {n.value.toLocaleString('en-IN')}
          </text>
        </g>
      ))}
      {R.map((n) => (
        <g key={`rt-${n.label}`}>
          <rect x={xR + 1} y={n.y} width={3} height={n.h} rx={1.5} fill="#c9c9c2" />
          <text x={xR + 12} y={n.y + n.h / 2 - 3} className="flow-label">
            {n.label}
          </text>
          <text x={xR + 12} y={n.y + n.h / 2 + 12} className="flow-value">
            {n.value.toLocaleString('en-IN')}
          </text>
        </g>
      ))}
    </svg>
  )
}
