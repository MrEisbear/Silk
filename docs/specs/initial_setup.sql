-- SQL Migration: Setup Job Permissions and Treasury Accounts

-- 1. Create Permissions Table
CREATE TABLE IF NOT EXISTS `permissions` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `permission_key` VARCHAR(64) UNIQUE NOT NULL,
  `description` VARCHAR(255)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 2. Create Job-Permissions Mapping Table
CREATE TABLE IF NOT EXISTS `job_permissions` (
  `job_id` INT NOT NULL,
  `permission_id` INT NOT NULL,
  PRIMARY KEY (`job_id`, `permission_id`),
  FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`),
  FOREIGN KEY (`permission_id`) REFERENCES `permissions` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 3. Insert Initial Permissions
INSERT INTO `permissions` (`permission_key`, `description`) VALUES
('access_treasury', 'Allows viewing and managing government accounts.'),
('issue_fines', 'Allows issuing fines.'),
('manage_licenses', 'Allows managing business licenses.');

-- 4. Map Treasurer Job to access_treasury Permission
-- Assumes 'Treasurer' job exists in 'jobs' table
INSERT INTO `job_permissions` (`job_id`, `permission_id`)
SELECT j.id, p.id FROM jobs j, permissions p
WHERE j.job_name = 'Treasurer' AND p.permission_key = 'access_treasury';

-- 5. Create Government Accounts
-- Assumes current database structure for `bank_accounts`
INSERT INTO `bank_accounts` (uuid, account_number, account_holder_type, account_holder_id, balance) VALUES
(uuid(), 'G-CENTRAL', 'gov', '0', 0.000),
(uuid(), 'G-TAXES', 'gov', '0', 0.000),
(uuid(), 'G-FINES', 'gov', '0', 0.000),
(uuid(), 'G-OTHER', 'gov', '0', 0.000);
