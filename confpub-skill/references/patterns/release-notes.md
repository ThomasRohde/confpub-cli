# Pattern: Release Notes

User-facing changelog with scannable structure, breaking-change callouts, and migration steps.

**Labels:** `release-notes`, plus product/service label

## Template

```markdown
---
labels:
  - release-notes
---

# Release v2.14.0 {status:Released|colour=Green}

**Release date:** 2026-03-20

::: panel Release Context
**Owner:** Payments Team · **Status:** {status:Released|colour=Green} · **Rollout:** 100% GA

**Highlights:**
- Payment gateway integration with Stripe and Adyen
- Checkout page load time reduced from 2.1s to 1.2s (P50)
- Reconciliation reporting for finance team
:::

{toc:maxLevel=2}

## New Features

### Payment Gateway Integration
Multi-provider payment processing with automatic failover.
Supports credit cards, SEPA direct debit, and Apple Pay.

### Reconciliation Reports
Daily reconciliation matching internal records against provider statements.
Available under **Reports → Payment Reconciliation**.

## Improvements

- Checkout load time: 2.1s → 1.2s (P50)
- Order confirmation emails within 5 seconds (was 2 minutes)
- Admin search supports fuzzy matching

## Bug Fixes

- Duplicate charges on double-click ({jira:PAY-189})
- JPY currency formatting ({jira:PAY-201})
- Webhook retry backoff ({jira:PAY-215})

## Breaking Changes

> [!CAUTION]
> `POST /api/v1/payments` is deprecated. Migrate to v2 before v2.16.0
> (2026-05-01). See [Migration Guide](Payment API v2 Migration Guide).

## Migration Steps

1. Update SDK: `pip install payments-sdk>=2.14.0` — verify with `pip show payments-sdk`
2. Replace `POST /api/v1/payments` with `POST /api/v2/payments` in all callers
3. Add `idempotency_key` header to every payment request — the v2 endpoint returns `400` without it
4. Run the integration suite against sandbox: `pytest tests/payments/ --env=sandbox` — all tests green before production

::: expand Full changelog
- `abc1234` feat: add Stripe provider
- `def5678` feat: add Adyen provider
- `ghi9012` perf: optimize checkout rendering
:::
```

## Tips

- Context panel at the top names the owner, rollout status, and key highlights so stakeholders can decide in seconds whether to read further.
- Jira links in bug fixes let readers jump straight to the ticket for context.
- Breaking changes get a `> [!CAUTION]` admonition — never bury them in a list.
- Full changelog in an expand block keeps the page scannable for non-developers.
