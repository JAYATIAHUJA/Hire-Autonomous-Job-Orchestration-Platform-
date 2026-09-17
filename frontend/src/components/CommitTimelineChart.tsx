import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TimelinePoint } from '../types'

export default function CommitTimelineChart({ timeline }: { timeline: TimelinePoint[] }) {
  if (timeline.length === 0) return null

  return (
    <section className="card">
      <h2>Commit activity</h2>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={timeline} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <XAxis dataKey="month" tick={{ fontSize: 11 }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="commits" fill="#4f46e5" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  )
}
