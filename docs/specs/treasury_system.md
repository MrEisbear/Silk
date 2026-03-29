# Treasury Account System Specification

## Objective
To centralize government funds and allow for transparent management of the treasury by appointed officials.

## Initial Government Accounts
Create four distinct government accounts for better organization:
- `Central Treasury`: For general government expenses.
- `Taxes`: For all incoming tax payments.
- `Fines`: For all late fees and fines.
- `Other Income`: For miscellaneous government income (e.g., licenses).

## Access & Permissions
The "Treasurer" job will be assigned the `access_treasury` permission. Users with this permission will be able to:
- Access their accessible government accounts via a new `/api/bank/gov/accounts` endpoint.
- Transfer funds between any government accounts.
- Make payments from a government account to a user's or company's account.

## Public Access
In line with the "socialism" principle:
- All `gov` accounts will have their balance and full transaction history visible via public API endpoints without requiring authentication.

### Public Endpoints:
- `GET /api/bank/public/gov/accounts`: List all government accounts.
- `GET /api/bank/public/gov/accounts/<uuid>/transactions`: List full transaction history for a specific government account.

## System Integration
- **Taxes:** All tax-related transactions will be automatically redirected to the "Taxes" government account.
- **Fines:** Any system-generated fines will be redirected to the "Fines" government account.
- **Other Income:** Any future income from government services will be redirected to the "Other Income" account.
