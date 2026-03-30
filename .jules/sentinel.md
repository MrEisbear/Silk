## 2025-05-15 - [IDOR in Transaction Retrieval]
**Vulnerability:** IDOR (Insecure Direct Object Reference) in `GET /api/bank/view-transactions/<uuid:tx_uuid>`.
**Learning:** Authenticated endpoints that fetch resources by UUID must still verify that the requester has permission to access that specific resource. UUIDs are not a substitute for authorization.
**Prevention:** Always include authorization logic in the database query (e.g., JOIN with ownership tables) or perform a check before returning data.
