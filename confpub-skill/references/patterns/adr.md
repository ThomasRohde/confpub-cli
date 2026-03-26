# Pattern: Architecture Decision Record (ADR)

Captures the "why" behind a technical decision. One page, one decision. Keep it short.

**Labels:** `adr`, `architecture`, plus domain (e.g., `data-platform`)

## Template

```markdown
---
labels:
  - adr
  - architecture
---

# ADR-NNN: Title of Decision {status:Accepted|colour=Green}

{toc:maxLevel=2}

::: panel Context
What problem triggered this decision, what constraints apply,
and why the team must decide now.
:::

## Decision Drivers

- Performance: P99 < 200ms at 10K RPS
- Team expertise: strong PostgreSQL, limited Cassandra
- Compliance: data residency in EU

## Options Considered

| Option | Pros | Cons | Effort |
|--------|------|------|--------|
| **PostgreSQL 16** | Familiar, ACID, strong tooling | Horizontal scaling limits | M |
| **CockroachDB** | Distributed, PG-compatible | Operational complexity, cost | L |
| **DynamoDB** | Fully managed, auto-scaling | Vendor lock-in, query limits | M |

## Decision

**We will use PostgreSQL 16** with read replicas and PgBouncer.

## Consequences

> [!TIP]
> **Positive:** Uses existing team expertise. Mature monitoring ecosystem.

> [!WARNING]
> **Risks:** Write throughput ceiling at ~50K TPS. Revisit if exceeded
> within 18 months. **Mitigation:** partition by tenant ID.

## Action Items

- [ ] Create migration plan from MySQL → PostgreSQL
- [ ] Set up PgBouncer in staging
- [ ] Update data residency documentation
- [ ] Schedule knowledge-sharing session

## Related

- [ADR-012: Connection Pooling](ADR-012 Connection Pooling)
- {jira:PLATFORM-456}
```

## Status Values

| Status | When to Use |
|--------|-------------|
| `{status:Proposed\|colour=Yellow}` | Under discussion |
| `{status:Accepted\|colour=Green}` | Decision made |
| `{status:Deprecated\|colour=Red}` | Superseded by newer ADR |
| `{status:Superseded\|colour=Red}` | Explicitly replaced |

## Tips

- ADRs are immutable once accepted. To change a decision, create a new ADR that supersedes the old one and update the old one's status to Deprecated/Superseded.
- Use the Options table for structured comparison — visible trade-offs reduce circular debate.
- Link to the Jira epic or ticket that triggered the decision for traceability.
