import { NOTICE_SECTIONS, NOTICE_TITLE, NOTICE_VERSION } from '../privacy/notice'

// Renders the same sections noticeText() hashes, so the accepted hash matches
// what was on screen.
export default function NoticeContent({ headingLevel = 2 }: { headingLevel?: 2 | 3 }) {
  const Title = headingLevel === 2 ? 'h2' : 'h3'
  const Section = headingLevel === 2 ? 'h3' : 'h4'
  return (
    <article className="notice-content" aria-labelledby="notice-title">
      <Title id="notice-title">{NOTICE_TITLE}</Title>
      <p className="muted notice-version">Version {NOTICE_VERSION}</p>
      {NOTICE_SECTIONS.map((section) => (
        <section key={section.heading}>
          <Section>{section.heading}</Section>
          {section.paragraphs?.map((p) => <p key={p}>{p}</p>)}
          {section.items && (
            <ul>
              {section.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </article>
  )
}
