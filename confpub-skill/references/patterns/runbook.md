# Pattern: Runbook / Playbook

Step-by-step operational procedures. Optimized for 3am incident response — clarity over elegance.

**Labels:** `runbook`, `operations`, plus service name

## Template

```markdown
---
labels:
  - runbook
  - operations
---

# Runbook: Procedure Name {status:Current|colour=Green}

::: panel Quick Reference
| Field | Value |
|-------|-------|
| **Service** | payment-service |
| **Owner** | @platform-oncall |
| **Last verified** | 2026-03-01 |
| **Escalation** | #incident-payments → @payments-lead |
| **Related alerts** | `PaymentLatencyP99 > 500ms`, `PaymentErrorRate > 1%` |
:::

> [!CAUTION]
> This runbook modifies production. Follow each step exactly.
> If unsure, escalate before proceeding.

{toc:maxLevel=2}

## Symptoms

- Alert `PaymentLatencyP99` firing
- Customer reports of slow checkout
- Error rate spike in Grafana

## Diagnosis

### Step 1: Check service health

```bash
kubectl get pods -n payments -l app=payment-service
kubectl top pods -n payments -l app=payment-service
```

**Expected:** All pods Running, CPU < 80%.

### Step 2: Check database connections

```sql
SELECT count(*), state FROM pg_stat_activity
WHERE datname = 'payments' GROUP BY state;
```

**Expected:** Active < 80. If > 100, see [Connection Pool Exhaustion](#connection-pool-exhaustion).

## Resolution Procedures

### Connection Pool Exhaustion

> [!WARNING]
> This kills active transactions. Coordinate before proceeding.

1. Identify stuck queries:
   ```sql
   SELECT pid, now() - query_start AS duration, query
   FROM pg_stat_activity
   WHERE state = 'active' AND now() - query_start > interval '5 minutes';
   ```

2. Terminate stuck connections:
   ```sql
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE state = 'active' AND now() - query_start > interval '30 minutes';
   ```

3. Restart PgBouncer:
   ```bash
   kubectl rollout restart deployment/pgbouncer -n payments
   ```

### Pod Crash Loop

::: expand Crash loop recovery steps
1. Check logs: `kubectl logs -n payments <pod> --previous`
2. Check events: `kubectl describe pod -n payments <pod>`
3. If OOM: increase memory limit
4. If app error: `kubectl rollout undo deployment/payment-service -n payments`
:::

## Verification

- [ ] All pods Running
- [ ] Health endpoint returns 200
- [ ] Error rate < 0.1%
- [ ] Latency P99 < 200ms

## Escalation Path

1. **L1:** On-call follows this runbook
2. **L2:** Service team lead
3. **L3:** VP Engineering — for customer-impacting > 30 minutes
```

## Tips

- The Quick Reference panel is crucial — during an incident, responders need owner/escalation/alerts at a glance.
- Use `> [!CAUTION]` before any destructive step.
- Every resolution section should end with a verification step.
- Use expand blocks for secondary procedures to keep the primary path scannable.
- Mark runbooks with `{status:Current|colour=Green}` or `{status:Needs Review|colour=Yellow}` — stale runbooks are dangerous.
