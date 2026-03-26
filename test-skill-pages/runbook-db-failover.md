# Runbook: PostgreSQL Database Failover {status:Current|colour=Green}

::: panel Quick Reference
| Field | Value |
|-------|-------|
| **Service** | Phoenix Payment Platform — PostgreSQL RDS |
| **Owner** | Squad Phoenix (Platform) |
| **Last verified** | 2026-03-20 |
| **Escalation** | #phoenix-incidents → @platform-lead → VP Engineering |
| **Related alerts** | `RDS-Phoenix-Primary-Unhealthy`, `PaymentDB-ReplicationLag > 30s` |
| **AWS Console** | eu-central-1 → RDS → phoenix-payments-primary |
:::

> [!CAUTION]
> This runbook involves production database operations. Incorrect execution
> can cause data loss or extended downtime. **Follow each step exactly.**
> If you are unsure at any point, stop and escalate to L2.

{toc:maxLevel=2}

## Symptoms

- PagerDuty alert: `RDS-Phoenix-Primary-Unhealthy`
- Application logs show `ConnectionRefused` or `timeout expired` for database connections
- Replication lag alert: `PaymentDB-ReplicationLag > 30s`
- Grafana dashboard shows payment transaction error rate > 5%

## Pre-Diagnosis Checklist

Before proceeding, confirm:

- [ ] You have AWS Console access with RDS permissions
- [ ] You are connected to the VPN (eu-central-1 access required)
- [ ] You have notified the #phoenix-incidents Slack channel
- [ ] You have the RDS master credentials from AWS Secrets Manager

## Diagnosis

### Step 1: Check RDS instance status

```bash
aws rds describe-db-instances \
  --db-instance-identifier phoenix-payments-primary \
  --query 'DBInstances[0].{Status:DBInstanceStatus,AZ:AvailabilityZone,MultiAZ:MultiAZ}' \
  --region eu-central-1
```

**Expected:** Status = `available`, MultiAZ = `true`

If Status is `failed` or `rebooting`, proceed to [Automated Failover](#automated-failover).
If Status is `available` but application can't connect, proceed to [Connection Issues](#connection-issues).

### Step 2: Check replication lag

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name ReplicaLag \
  --dimensions Name=DBInstanceIdentifier,Value=phoenix-payments-replica \
  --start-time $(date -u -d '10 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 --statistics Average \
  --region eu-central-1
```

**Expected:** ReplicaLag < 5 seconds.

| Lag | Severity | Action |
|-----|----------|--------|
| < 5s | Normal | No action needed |
| 5–30s | {status:Warning\|colour=Yellow} | Monitor, check for long-running queries |
| 30s–5m | {status:High\|colour=Red} | Investigate write load, see [Replication Lag](#replication-lag) |
| > 5m | {status:Critical\|colour=Red} | Escalate to L2 immediately |

### Step 3: Check PgBouncer

```bash
kubectl exec -it deploy/pgbouncer -n phoenix -- pgbouncer -R
kubectl exec -it deploy/pgbouncer -n phoenix -- psql -p 6432 pgbouncer -c "SHOW POOLS;"
```

**Expected:** `sv_active` < 80% of `max_server_connections`.

## Resolution Procedures

### Automated Failover

RDS Multi-AZ handles most failovers automatically. This procedure is for when you need to verify and support the automated process.

1. **Confirm failover is in progress:**
   ```bash
   aws rds describe-events \
     --source-identifier phoenix-payments-primary \
     --source-type db-instance \
     --duration 30 \
     --region eu-central-1
   ```
   Look for: `Multi-AZ instance failover started` or `Multi-AZ instance failover completed`

2. **Monitor the failover** (typically 60–120 seconds):
   ```bash
   watch -n 5 "aws rds describe-db-instances \
     --db-instance-identifier phoenix-payments-primary \
     --query 'DBInstances[0].DBInstanceStatus' \
     --region eu-central-1 --output text"
   ```

3. **After failover completes**, restart PgBouncer to clear stale connections:
   ```bash
   kubectl rollout restart deployment/pgbouncer -n phoenix
   ```

4. **Verify application recovery** — wait 2 minutes, then:
   ```bash
   curl -s https://phoenix-api.internal/health | jq '.database'
   ```

> [!WARNING]
> If automated failover does not complete within 5 minutes, escalate to L2.
> Do NOT attempt manual failover without L2 approval.

### Connection Issues

When RDS is healthy but the application can't connect:

::: expand Step-by-step connection troubleshooting

1. **Check PgBouncer pool exhaustion:**
   ```bash
   kubectl exec -it deploy/pgbouncer -n phoenix -- \
     psql -p 6432 pgbouncer -c "SHOW POOLS;" | grep phoenix
   ```
   If `sv_active` equals `max_server_connections`, connections are exhausted.

2. **Kill idle connections:**
   ```sql
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE datname = 'phoenix_payments'
     AND state = 'idle'
     AND state_change < NOW() - INTERVAL '10 minutes';
   ```

3. **Restart PgBouncer:**
   ```bash
   kubectl rollout restart deployment/pgbouncer -n phoenix
   ```

4. **If still failing**, check security groups and network ACLs:
   ```bash
   aws ec2 describe-security-groups \
     --group-ids sg-phoenix-rds \
     --query 'SecurityGroups[0].IpPermissions' \
     --region eu-central-1
   ```
:::

### Replication Lag

::: expand Addressing replication lag > 30 seconds

1. **Check for long-running queries on primary:**
   ```sql
   SELECT pid, now() - query_start AS duration, left(query, 100)
   FROM pg_stat_activity
   WHERE state = 'active'
     AND datname = 'phoenix_payments'
   ORDER BY duration DESC LIMIT 10;
   ```

2. **Check for vacuum operations:**
   ```sql
   SELECT relname, last_autovacuum, last_autoanalyze
   FROM pg_stat_user_tables
   WHERE schemaname = 'public'
   ORDER BY last_autovacuum DESC NULLS LAST LIMIT 10;
   ```

3. **If write load is the cause**, consider temporarily routing read traffic away from the replica:
   ```bash
   kubectl set env deployment/phoenix-api -n phoenix READ_REPLICA_ENABLED=false
   ```

> [!NOTE]
> Re-enable the read replica once lag returns to < 5 seconds:
> `kubectl set env deployment/phoenix-api -n phoenix READ_REPLICA_ENABLED=true`
:::

## Verification

After any resolution, verify all of the following:

- [ ] RDS instance status is `available`
- [ ] Replication lag < 5 seconds
- [ ] PgBouncer shows healthy connection pool
- [ ] Application health endpoint returns `{"database": "ok"}`
- [ ] Payment transaction error rate < 0.1% (Grafana)
- [ ] No new alerts firing in PagerDuty

## Escalation Path

| Level | Who | When |
|-------|-----|------|
| **L1** | On-call engineer | First responder — follow this runbook |
| **L2** | @platform-lead | Automated failover fails, or > 15 min unresolved |
| **L3** | VP Engineering + AWS Support | Customer-impacting > 30 min, or data loss risk |

> [!TIP]
> When escalating, include: current RDS status, replication lag, error rate,
> and what steps you've already taken. Copy the relevant AWS CLI output.
