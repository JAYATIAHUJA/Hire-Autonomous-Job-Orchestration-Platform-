import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TimelinePoint } from '../types'

export default function CommitTimelineChart({ timeline }: { timeline: TimelinePoint[] }) {
  if (timeline.length === 0) return null

  return (
    <section className="card card-pad">
      <h3>When you shipped</h3>
      <p className="muted small" style={{ margin: '4px 0 12px' }}>
        Your commits per month.
      </p>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={timeline} margin={{ top: 4, right: 0, left: -24, bottom: 0 }}>
          <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#7d818a' }} axisLine={false} tickLine={false} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#7d818a' }} axisLine={false} tickLine={false} />
          <Tooltip
            cursor={{ fill: 'rgba(17,17,19,0.04)' }}
            contentStyle={{ background: '#111113', color: '#fff', borderRadius: 10, border: 'none', fontSize: 12 }}
            itemStyle={{ color: '#fff' }}
          />
          <Bar dataKey="commits" fill="#111113" radius={[5, 5, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  )
}
