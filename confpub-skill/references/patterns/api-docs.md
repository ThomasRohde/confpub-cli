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

::: panel Base URL
`https://api.example.com/v2`

Authentication: Bearer token in `Authorization` header.
Rate limit: 1000 req/min per API key.
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

### Get / Update / Delete

`GET /resources/{id}`
`PATCH /resources/{id}`
`DELETE /resources/{id}`

> [!WARNING]
> Deletion is permanent. Consider `{"status": "archived"}` instead.

## Error Codes

| Code | Meaning | Retryable |
|------|---------|-----------|
| 400 | Validation failed | No |
| 401 | Invalid token | No |
| 404 | Not found | No |
| 429 | Rate limited | Yes (`Retry-After` header) |
| 500 | Server error | Yes (exponential backoff) |

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

- Panel with base URL and auth info is the first thing developers need.
- Expand blocks for SDKs keep the page focused on the API contract.
- `> [!WARNING]` on destructive endpoints prevents accidents.
- Error table with "Retryable" column helps automated clients.
