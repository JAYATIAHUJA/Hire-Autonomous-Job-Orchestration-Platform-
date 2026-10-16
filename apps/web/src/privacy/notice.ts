// DPDP notice v1. The page renders these sections and the consent call sends the
// sha256 of noticeText(), so what the user read and what we record are the same
// bytes. Any wording change, even a typo, must bump NOTICE_VERSION so existing
// users are asked again.

export const NOTICE_VERSION = 'v1'

export const NOTICE_TITLE = 'How Hire uses your personal data'

// Placeholder until the grievance officer is appointed. Filling it in changes the
// notice text, so it ships as a new version.
export const GRIEVANCE_CONTACT = '[PLACEHOLDER: Grievance Officer name and email, to be confirmed before launch]'

export type NoticeSection = {
  heading: string
  paragraphs?: string[]
  items?: string[]
}

export const NOTICE_SECTIONS: NoticeSection[] = [
  {
    heading: 'Who we are',
    paragraphs: [
      'Hire helps you find jobs and apply to them. This notice explains what personal data we use, why, for how long, who we share it with, and your rights under India’s Digital Personal Data Protection Act, 2023. We show it before we collect anything beyond what you need to sign in.',
    ],
  },
  {
    heading: 'What we collect and why',
    items: [
      'Your sign-in details (your email address, or the GitHub or Google account you sign in with), to log you in and keep you signed in. Hire cannot work without this.',
      'If you turn on GitHub analysis: your public GitHub repositories, commits and pull requests, to build your proof-of-work skills profile. We never read private repositories unless you separately choose to include them.',
      'If you turn on resume parsing: the resume file you upload and the facts we extract from it, to suggest profile facts. Nothing we extract is used until you approve it.',
      'If you turn on email ingest (coming later): recruiter replies in a mailbox you connect, to keep your application board up to date. This is not available yet; turning it on now only records your choice.',
      'The preferences and standard answers you type in (for example notice period, expected salary and work authorisation), to rank jobs for you and to fill application forms that you review before they are sent.',
    ],
  },
  {
    heading: 'How long we keep it',
    paragraphs: [
      'We keep your data while your account is open. If you erase your account, we delete your profile, facts, resume file, answers and preferences within 30 days. We keep a record of the consents you gave and of applications you approved only as long as the law requires.',
    ],
  },
  {
    heading: 'Who we share it with',
    items: [
      'Employers: only the application you approve, sent only to the employer you applied to.',
      'Service providers that run Hire for us, such as cloud hosting and our AI provider (Anthropic), which reads your resume to suggest facts. They may use your data only to provide that service to us.',
      'We do not sell your personal data.',
    ],
  },
  {
    heading: 'Your rights',
    items: [
      'Access: ask for a summary of the personal data we hold about you and how we use it.',
      'Correct: fix or complete anything that is wrong.',
      'Erase: delete your account and your data.',
      'Withdraw consent: switch off any optional use at any time, as easily as you switched it on. This stops that use from then on.',
      'Nominate: name someone to exercise these rights for you if you cannot.',
      `Complain: contact our Grievance Officer at ${GRIEVANCE_CONTACT}. If you are not satisfied with the answer, you can complain to the Data Protection Board of India.`,
    ],
  },
  {
    heading: 'Your choices',
    paragraphs: [
      'Each optional use has its own switch, and every switch starts off. Saying no to one does not stop you using the rest of Hire.',
    ],
  },
]

// The exact text the hash covers: title, version, then each section's heading
// and lines, in display order.
export function noticeText(sections: NoticeSection[] = NOTICE_SECTIONS): string {
  const parts = [`${NOTICE_TITLE}\nVersion ${NOTICE_VERSION}`]
  for (const section of sections) {
    const lines = [...(section.paragraphs ?? []), ...(section.items ?? []).map((item) => `- ${item}`)]
    parts.push([section.heading, ...lines].join('\n'))
  }
  return parts.join('\n\n')
}
