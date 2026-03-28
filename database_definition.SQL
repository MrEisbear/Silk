-- silk.bank_accounts definition

CREATE TABLE `bank_accounts` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `uuid` char(36) NOT NULL DEFAULT uuid(),
  `account_number` varchar(32) NOT NULL,
  `account_holder_type` enum('user','company','gov') NOT NULL,
  `account_holder_id` varchar(36) NOT NULL,
  `balance` decimal(19,3) NOT NULL DEFAULT 0.000,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `is_frozen` tinyint(1) NOT NULL DEFAULT 0,
  `is_deleted` tinyint(1) NOT NULL DEFAULT 0,
  `pin_hash` varchar(255) DEFAULT NULL,
  `pin_failed_attempts` int(11) NOT NULL DEFAULT 0,
  `pin_locked_until` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `account_number` (`account_number`),
  UNIQUE KEY `unique_uuid` (`uuid`),
  KEY `idx_holder` (`account_holder_type`,`account_holder_id`)
) ENGINE=InnoDB AUTO_INCREMENT=26 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- silk.gift_codes definition

CREATE TABLE `gift_codes` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(32) NOT NULL,
  `amount` decimal(19,3) NOT NULL CHECK (`amount` > 0),
  `currency` char(3) NOT NULL DEFAULT 'BCD',
  `created_by` char(36) NOT NULL,
  `redeemed_by` char(36) DEFAULT NULL,
  `redeemed_at` datetime DEFAULT NULL,
  `expires_at` datetime NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  KEY `idx_code` (`code`),
  KEY `idx_redeemed` (`redeemed_by`),
  KEY `idx_expires` (`expires_at`)
) ENGINE=InnoDB AUTO_INCREMENT=54 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- silk.salary_classes definition

CREATE TABLE `salary_classes` (
  `class_level` tinyint(4) NOT NULL,
  `daily_amount` decimal(19,3) NOT NULL,
  PRIMARY KEY (`class_level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- silk.tokens definition

CREATE TABLE `tokens` (
  `token` varchar(64) NOT NULL,
  `sender_uuid` uuid NOT NULL,
  `recipient_uuid` uuid NOT NULL,
  `amount` decimal(19,3) NOT NULL,
  `tax` tinyint(4) NOT NULL DEFAULT 1,
  `label` varchar(255) DEFAULT NULL,
  `webhook_url` text DEFAULT NULL,
  `status` enum('issued','used','expired','revoked') NOT NULL DEFAULT 'issued',
  `created` datetime NOT NULL DEFAULT current_timestamp(),
  `expires` datetime NOT NULL,
  `used_at` datetime DEFAULT NULL,
  `ip_address` varchar(45) DEFAULT NULL,
  `user_agent` text DEFAULT NULL,
  PRIMARY KEY (`token`),
  KEY `idx_tokens_expires_status` (`expires`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- silk.users definition

CREATE TABLE `users` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `uuid` char(36) NOT NULL,
  `username` varchar(64) NOT NULL,
  `email` varchar(128) DEFAULT NULL,
  `password_hash` varchar(255) DEFAULT NULL,
  `discord_id` bigint(20) DEFAULT NULL,
  `avatar_url` text DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `last_login` datetime DEFAULT NULL,
  `is_verified` tinyint(1) DEFAULT 0,
  `is_banned` tinyint(1) DEFAULT 0,
  `manual` tinyint(1) DEFAULT 0,
  `last_salary_claim` datetime DEFAULT NULL,
  `role` enum('user','mod','admin') DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uuid` (`uuid`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- silk.jobs definition

CREATE TABLE `jobs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `job_name` varchar(64) NOT NULL,
  `department` varchar(64) DEFAULT NULL,
  `salary_class` tinyint(4) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_job_salary` (`salary_class`),
  CONSTRAINT `fk_job_salary` FOREIGN KEY (`salary_class`) REFERENCES `salary_classes` (`class_level`)
) ENGINE=InnoDB AUTO_INCREMENT=43 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- silk.transactions definition

CREATE TABLE `transactions` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `uuid` char(36) NOT NULL DEFAULT uuid(),
  `transaction_type` enum('transfer','payment','automated','chargeback','salary','billing','deposit','withdrawal','fee','fine','tax','dividend','refund','adjustment','giftcard') NOT NULL,
  `from_account_id` bigint(20) unsigned DEFAULT NULL,
  `to_account_id` bigint(20) unsigned DEFAULT NULL,
  `amount` decimal(19,3) NOT NULL CHECK (`amount` > 0),
  `tax_category` tinyint(1) NOT NULL DEFAULT 0,
  `description` varchar(255) DEFAULT NULL,
  `metadata` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`metadata`)),
  `confirmed` tinyint(1) NOT NULL DEFAULT 0,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_from` (`from_account_id`),
  KEY `idx_to` (`to_account_id`),
  KEY `idx_created` (`created_at`),
  KEY `idx_transactions_from_date` (`from_account_id`,`created_at` DESC,`id` DESC),
  KEY `idx_transactions_to_date` (`to_account_id`,`created_at` DESC,`id` DESC),
  CONSTRAINT `transactions_ibfk_1` FOREIGN KEY (`from_account_id`) REFERENCES `bank_accounts` (`id`) ON DELETE SET NULL,
  CONSTRAINT `transactions_ibfk_2` FOREIGN KEY (`to_account_id`) REFERENCES `bank_accounts` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=140 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- silk.user_jobs definition

CREATE TABLE `user_jobs` (
  `user_uuid` char(36) NOT NULL,
  `job_id` int(11) NOT NULL,
  PRIMARY KEY (`user_uuid`,`job_id`),
  KEY `fk_uj_job` (`job_id`),
  CONSTRAINT `fk_uj_job` FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`),
  CONSTRAINT `fk_uj_user` FOREIGN KEY (`user_uuid`) REFERENCES `users` (`uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;