## 2025-05-22 - IDOR in Transaction Retrieval
**Vulnerability:** Insecure Direct Object Reference (IDOR) in `get_transaction` endpoint.
**Learning:** Authenticated endpoints retrieving resources by UUID (like transactions) were lacking ownership or role-based checks, allowing any logged-in user to access sensitive data by enumerating UUIDs.
**Prevention:** Always implement an authorization check that verifies if the requesting user is the resource owner, a participant, or has an administrative role. Fail securely by returning a 404 error on unauthorized access to prevent resource enumeration.
