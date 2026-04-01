## 2025-05-15 - Clarification on Transaction Visibility Policy
**Vulnerability:** Initially identified as an IDOR in the transaction details endpoint, the policy was clarified to allow any authenticated user to view specific transactions via UUID to prevent bots/scraping while maintaining relative privacy through the use of UUIDs.
**Learning:** Understanding the intended privacy model (security through obscurity combined with authentication) is crucial before applying restrictive authorization.
**Prevention:** Explicitly document visibility policies for all resources to avoid confusion between intended behavior and vulnerabilities.
