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
          <Tooltip contentStyle={{ background: '#121316', color: '#fff', borderRadius: 8, border: 'none', fontSize: 12 }} />
          <Bar dataKey="commits" fill="#121316" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  )
}
