-- =========================
-- PLAYERS TABLE
-- =========================

ALTER TABLE `players`
  ADD COLUMN `elo` INT UNSIGNED NOT NULL DEFAULT 1000;

ALTER TABLE `players`
  ADD COLUMN `wins` INT UNSIGNED NOT NULL DEFAULT 0;

ALTER TABLE `players`
  ADD COLUMN `losses` INT UNSIGNED NOT NULL DEFAULT 0;

ALTER TABLE `players`
  ADD COLUMN `games_played` INT UNSIGNED NOT NULL DEFAULT 0;

ALTER TABLE `players`
  ADD COLUMN `elo_timed` INT UNSIGNED NOT NULL DEFAULT 1000;

ALTER TABLE `players`
  ADD COLUMN `elo_streak` INT UNSIGNED NOT NULL DEFAULT 1000;

-- indexes (safe only if not already exists)
ALTER TABLE `players`
  ADD INDEX `idx_elo_timed` (`elo_timed`);

ALTER TABLE `players`
  ADD INDEX `idx_elo_streak` (`elo_streak`);

-- =========================
-- MATCHES TABLE
-- =========================

ALTER TABLE `matches`
  ADD COLUMN `game_mode` ENUM('classic','timed','streak') NOT NULL DEFAULT 'classic';

ALTER TABLE `matches`
  MODIFY COLUMN `game_mode` ENUM('classic','timed','streak') NOT NULL DEFAULT 'classic';

-- =========================
-- MATCH RESULTS
-- =========================

ALTER TABLE `match_results`
  ADD COLUMN `player1_score` INT UNSIGNED NOT NULL DEFAULT 0;

ALTER TABLE `match_results`
  ADD COLUMN `player2_score` INT UNSIGNED NOT NULL DEFAULT 0;

-- =========================
-- DAILY RESULTS
-- =========================

CREATE TABLE IF NOT EXISTS `daily_results` (
  `player_id` BIGINT UNSIGNED NOT NULL,
  `date` DATE NOT NULL,
  `solved` TINYINT(1) NOT NULL DEFAULT 0,
  `guess_count` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `guesses` VARCHAR(40) NOT NULL DEFAULT '',
  `completed_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`player_id`, `date`),
  KEY `idx_date` (`date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================
-- FRIENDS SYSTEM
-- =========================

CREATE TABLE IF NOT EXISTS `friends` (
  `player_id` BIGINT UNSIGNED NOT NULL,
  `friend_id` BIGINT UNSIGNED NOT NULL,
  `status` ENUM('pending','accepted') NOT NULL DEFAULT 'pending',
  `created_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`player_id`, `friend_id`),
  KEY `friend_id` (`friend_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;