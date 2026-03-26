# Pattern: API Documentation

Endpoint reference with request/response examples, error codes, and SDK snippets.

**Labels:** `api-docs`, `technical`, plus service label

## Template

```markdown
---
labels:
  - api-docs
  - technical
---

# API: Service Name v2 {status:Stable|colour=Green}

::: panel Overview
**Base URL:** `https://api.example.com/v2`
**Owner:** Platform team (`#platform-eng` in Slack)
**Authentication:** Bearer token in `Authorization` header.
**Rate limit:** 1000 req/min per API key.
:::

{toc:maxLevel=2}

## Endpoints

### Create Resource

`POST /resources`

```json
{
  "name": "my-resource",
  "type": "standard",
  "config": { "timeout_ms": 5000 }
}
```

**Response (201):**
```json
{
  "id": "res_abc123",
  "name": "my-resource",
  "created_at": "2026-03-20T14:00:00Z"
}
```

### List Resources

`GET /resources?page=1&per_page=20`

**Response (200):**
```json
{
  "data": [ { "id": "res_abc123", "name": "my-resource" } ],
  "pagination": { "page": 1, "per_page": 20, "total": 1 }
}
```

### Get Resource

`GET /resources/{id}`

**Response (200):**
```json
{
  "id": "res_abc123",
  "name": "my-resource",
  "type": "standard",
  "config": { "timeout_ms": 5000 },
  "created_at": "2026-03-20T14:00:00Z"
}
```

### Update Resource

`PATCH /resources/{id}`

```json
{
  "config": { "timeout_ms": 10000 }
}
```

**Response (200):** Returns the full updated resource.

### Delete Resource

`DELETE /resources/{id}`

**Response (204):** No body.

> [!WARNING]
> Deletion is permanent. Consider `PATCH` with `{"status": "archived"}` instead.

## Error Codes

| Code | Meaning | Retryable |
|------|---------|-----------|
| 400 | Validation failed | {status:No\|colour=Red} |
| 401 | Invalid token | {status:No\|colour=Red} |
| 404 | Not found | {status:No\|colour=Red} |
| 429 | Rate limited | {status:Yes\|colour=Green} — honor `Retry-After` header |
| 500 | Server error | {status:Yes\|colour=Green} — use exponential backoff |

## SDKs

::: expand Python
```python
from service_sdk import Client
client = Client(api_key="key")
resource = client.resources.create(name="test")
```
:::

::: expand JavaScript
```javascript
import { Client } from '@org/service-sdk';
const client = new Client({ apiKey: 'key' });
const resource = await client.resources.create({ name: 'test' });
```
:::
```

## Tips

- Open with a panel containing base URL, owner, auth method, and rate limits — developers look for these first.
- Give every endpoint its own heading with a request example and response shape so readers can scan independently.
- Use expand blocks for SDK snippets to keep the page focused on the HTTP contract.
- Mark destructive endpoints with `> [!WARNING]` and suggest a safer alternative.
- Use status lozenges in the error table's Retryable column (escape `\|` inside table cells).
