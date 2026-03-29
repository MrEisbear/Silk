# Job Permissions System Specification

## Objective
To implement a flexible, role-based permission system tied to the existing job system. This allows for granular control over API access for different roles like "Treasurer," "Police Chief," etc.

## Database Schema Changes

### `permissions` Table
Stores all possible permissions in the system.
```sql
CREATE TABLE `permissions` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `permission_key` VARCHAR(64) UNIQUE NOT NULL,
  `description` VARCHAR(255)
);
```

### `job_permissions` Table
Maps jobs to permissions.
```sql
CREATE TABLE `job_permissions` (
  `job_id` INT NOT NULL,
  `permission_id` INT NOT NULL,
  PRIMARY KEY (`job_id`, `permission_id`),
  FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`),
  FOREIGN KEY (`permission_id`) REFERENCES `permissions` (`id`)
);
```

## Logic Implementation

### `require_permission` Decorator
A new decorator to be added to `core/coreAuthUtil.py` that checks if the authenticated user's jobs grant them a specific permission.

```python
def require_permission(permission_key: str):
    def decorator(func):
        @wraps(func)
        @require_token
        def wrapper(data, *args, **kwargs):
            user_uuid = data.get("uuid")
            with db_helper.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM user_jobs uj
                    JOIN job_permissions jp ON uj.job_id = jp.job_id
                    JOIN permissions p ON jp.permission_id = p.id
                    WHERE uj.user_uuid = %s AND p.permission_key = %s
                """, (user_uuid, permission_key))
                if not cur.fetchone():
                    return jsonify({"error": f"Missing permission: {permission_key}"}), 403
            return func(data, *args, **kwargs)
        return wrapper
    return decorator
```

## Initial Permissions
- `access_treasury`: Allows viewing and managing government accounts.
- `issue_fines`: (Future) Allows police officers to issue fines.
- `manage_licenses`: (Future) Allows government officials to manage business licenses.
