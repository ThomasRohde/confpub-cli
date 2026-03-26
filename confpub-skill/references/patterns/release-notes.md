# Pattern: Release Notes

User-facing changelog. Professional, scannable, with migration steps.

**Labels:** `release-notes`, plus product/service label

## Template

```markdown
---
labels:
  - release-notes
---

# Release v2.14.0 {status:Released|colour=Green}

**Release date:** 2026-03-20

::: panel Highlights
- Payment gateway integration with Stripe and Adyen
- 40% improvement in checkout page load time
- New reconciliation reporting for finance team
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

1. Update SDK: `pip install payments-sdk>=2.14.0`
2. Replace v1 endpoints with v2
3. Add `idempotency_key` header to payment requests
4. Test in sandbox before production

::: expand Full changelog
- `abc1234` feat: add Stripe provider
- `def5678` feat: add Adyen provider
- `ghi9012` perf: optimize checkout rendering
:::
```

## Tips

- Highlights panel at the top lets stakeholders skip the details.
- Jira links in bug fixes provide traceability.
- Breaking changes get a `> [!CAUTION]` admonition — never bury them.
- Full changelog in an expand block keeps the page scannable.
