## 2025-05-15 - IDOR in Transaction Details Endpoint
**Vulnerability:** The `/api/bank/view-transactions/<uuid:tx_uuid>` endpoint lacked any authorization checks, allowing any authenticated user to view details of any transaction in the system if they knew or guessed the transaction UUID.
**Learning:** While some transaction listing endpoints had checks, the individual resource retrieval endpoint was overlooked, likely due to a focus on UUIDs being "unguessable".
**Prevention:** Always verify that the requester has ownership of the resource or a valid administrative role, even when using UUIDs.
