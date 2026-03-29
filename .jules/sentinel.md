## 2026-03-29 - [IDOR in Transaction Details]
**Vulnerability:** Insecure Direct Object Reference (IDOR) on `/api/bank/view-transactions/<uuid:tx_uuid>`. Any authenticated user could view full details of any transaction by its UUID.
**Learning:** Authentication alone (`@require_token`) is insufficient for resource-specific endpoints. Ownership or authorization checks must be explicitly implemented.
**Prevention:** Always verify that the authenticated user is authorized to access the specific resource (e.g., they are a party to the transaction, an admin, or the resource is public) before returning data.
