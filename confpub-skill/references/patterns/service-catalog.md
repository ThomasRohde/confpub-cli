# Pattern: Service Catalog Entry

Standard template for documenting a service in the organization's catalog.

**Labels:** `service-catalog`, plus team/domain label

## Template

```markdown
---
labels:
  - service-catalog
  - platform
---

# Service: payment-service {status:Production|colour=Green}

::: panel Quick Facts
| | |
|---|---|
| **Owner** | Squad Payments (@payments-lead) |
| **Slack** | #payments-support |
| **On-call** | PagerDuty: payments-oncall |
| **Repo** | [github.com/org/payment-service](https://github.com/org/payment-service) |
| **Tier** | {status:Tier 1\|colour=Red} (Revenue-critical) |
:::

{toc:maxLevel=2}

## Overview

::: excerpt
The payment-service handles charge creation, refunds, and status tracking.
Integrates with Stripe and Adyen with automatic failover.
:::

## Architecture

:::: layout two-equal
::: cell
### Dependencies (consumes)
- **auth-service** — Token validation
- **user-service** — Customer lookup
- **PostgreSQL** — Payment records
- **Redis** — Idempotency cache
:::
::: cell
### Dependents (consumed by)
- **checkout-frontend** — Payment initiation
- **order-service** — Payment status
- **finance-service** — Reconciliation
:::
::::

## SLOs

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Availability | 99.95% | 99.97% | {status:Met\|colour=Green} |
| Latency P99 | < 500ms | 342ms | {status:Met\|colour=Green} |
| Error Rate | < 0.1% | 0.03% | {status:Met\|colour=Green} |

## Runbooks

- [Payment Processing Failures](Runbook Payment Failures)
- [Database Connection Exhaustion](Runbook DB Connections)
- [Provider Failover](Runbook Provider Failover)

## API Documentation

{include:Payment Service API Reference}

{children}
```

## Tips

- The excerpt block lets other pages include the service summary via `{excerpt-include:...}`.
- Two-column Dependencies layout shows the service's position in the architecture.
- SLO table with lozenges gives instant health visibility.
- `{children}` at the bottom auto-lists sub-pages (runbooks, API docs, etc.).
