# ADR-008: Launch decisions (PLAN.md §19)

- Status: Accepted (2026-10-15). The owner accepted every recommendation; any of them can be revisited with a new ADR.

| # | Topic | Decision |
|---|---|---|
| 1 | Default apply mode | Review each for the first 10, then offer opt-in Autopilot (ADR-005). |
| 2 | Browser runtime | Self-hosted OpenBot fork behind a `ComputerProvider` interface. A Browserbase or Steel adapter is kept only for overflow and experiments. |
| 3 | LinkedIn and Naukri | Assisted Apply only, never automated (ADR-001). |
| 4 | Models | `claude-opus-5-5` everywhere at launch (about ₹55 per application). Move triage, JD extraction or mail classification to `claude-sonnet-5-5` or `claude-haiku-5-5` only after an eval shows quality holds. Use the Batch API and prompt caching from the start. |
| 5 | Launch market | India plus remote-global roles. The deck ranks India roles first; remote-global roles must accept candidates located in India. |
| 6 | Employer disclosure | **On by default**: "Submitted with the help of Hire. The candidate reviewed this application." The user can turn it off. |
| 7 | Pricing | Free; Plus ₹499/month (25 auto-applications); Pro ₹999/month (60, Autopilot); ₹199 for 10-application packs and a ₹199/week plan. Credits are charged **only on confirmed submission**. |
| 8 | Ownership and licence | Proprietary, all rights reserved. Needs a written ownership agreement among the three original Hire contributors before any external release. |

## Consequences
- The answer-bank seed and eligibility gates must handle remote-global roles (work authorisation, time zones, currency).
- Disclosure text goes into the Tier A adapters as an optional "additional information" field and into Assisted Apply packets.
- Cost dashboards must split spend by model route, so the decision 4 eval has data.
