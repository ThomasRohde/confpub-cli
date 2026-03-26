# Pattern: Onboarding Guide

Progressive checklist that takes a new team member from zero access to first contribution in two weeks. Task lists make every step trackable.

**Labels:** `onboarding`, `team-guide`, `active`, plus team label

## Template

```markdown
---
labels:
  - onboarding
  - team-guide
  - active
---

# Onboarding: Squad Name

::: panel Onboarding — Squad Name {status:Active|colour=Green}
**Owner:** @tech-lead | **Audience:** New squad members | **Timeline:** 2 weeks

Work through this guide top to bottom — each section builds on the previous.
:::

{toc}

## Day 1: Access & Environment

- [ ] Join Slack: #squad-name, #squad-name-alerts
- [ ] Request access: GitHub, Jira, Confluence space
- [ ] Set up dev environment: [Dev Setup Guide](Dev Setup Guide)
- [ ] Verify VPN access to staging

## Day 2–3: Codebase

- [ ] Read [Architecture Overview](Architecture Overview)
- [ ] Clone and build the primary service
- [ ] Run the test suite locally
- [ ] Review 5 recent merged PRs for code style

::: expand Key architecture decisions
- [ADR-001: Database Choice](ADR-001 Database Choice)
- [ADR-005: Event Sourcing](ADR-005 Event Sourcing)
- [ADR-012: API Versioning](ADR-012 API Versioning)
:::

## Week 1: First Contribution

- [ ] Pick a "good first issue" from Jira
- [ ] Pair with onboarding buddy
- [ ] Submit first PR
- [ ] Attend sprint ceremonies

## Week 2: Depth

- [ ] Shadow an on-call shift
- [ ] Read service runbooks
- [ ] Review last quarter's post-mortems
- [ ] Present "what I learned" at standup

## Key Contacts

| Role | Person | When to Contact |
|------|--------|----------------|
| Onboarding buddy | @buddy | Anything — first contact |
| Tech lead | @tech-lead | Architecture, PR reviews |
| Scrum master | @sm | Process, blockers |
| Product owner | @po | Requirements, priorities |
```

## Tips

- The context panel states owner, audience, status, and timeline so a reader knows instantly whether this guide applies to them.
- Task lists make progress trackable — the new hire checks items off as they go.
- Expand blocks for ADRs keep the page focused on actions, not reading.
- Key Contacts table prevents the "who do I ask?" problem.
- Include a lifecycle label (`active`) so stale guides surface in label-based searches.
- Link to existing pages rather than duplicating content.
