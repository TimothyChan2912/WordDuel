-- Run this against an existing WordDuel database to add new columns
ALTER TABLE `players`
  ADD COLUMN IF NOT EXISTS `elo`          INT UNSIGNED NOT NULL DEFAULT 1000,
  ADD COLUMN IF NOT EXISTS `wins`         INT UNSIGNED NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS `losses`       INT UNSIGNED NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS `games_played` INT UNSIGNED NOT NULL DEFAULT 0;

ALTER TABLE `matches`
  ADD COLUMN IF NOT EXISTS `game_mode` ENUM('classic','timed','streak','battle') NOT NULL DEFAULT 'classic';

-- Add newer modes to existing installations (safe to re-run)
ALTER TABLE `matches`
  MODIFY COLUMN `game_mode` ENUM('classic','timed','streak','battle') NOT NULL DEFAULT 'classic';

ALTER TABLE `match_results`
  ADD COLUMN IF NOT EXISTS `player1_score` INT UNSIGNED NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS `player2_score` INT UNSIGNED NOT NULL DEFAULT 0;

-- Per-mode ELO columns (run once on existing installs)
ALTER TABLE `players`
  ADD COLUMN IF NOT EXISTS `elo_timed`  INT UNSIGNED NOT NULL DEFAULT 1000,
  ADD COLUMN IF NOT EXISTS `elo_streak` INT UNSIGNED NOT NULL DEFAULT 1000,
  ADD COLUMN IF NOT EXISTS `elo_battle` INT UNSIGNED NOT NULL DEFAULT 1000;
ALTER TABLE `players`
  ADD INDEX `idx_elo_timed`  (`elo_timed`),
  ADD INDEX `idx_elo_streak` (`elo_streak`),
  ADD INDEX `idx_elo_battle` (`elo_battle`);

-- Daily challenge results (safe to re-run)
CREATE TABLE IF NOT EXISTS `daily_results` (
  `player_id`    BIGINT UNSIGNED  NOT NULL,
  `date`         DATE             NOT NULL,
  `solved`       TINYINT(1)       NOT NULL DEFAULT 0,
  `guess_count`  TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `guesses`      VARCHAR(40)      NOT NULL DEFAULT '',
  `completed_at` TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`player_id`, `date`),
  KEY `idx_date` (`date`),
  CONSTRAINT `dr_fk_player` FOREIGN KEY (`player_id`) REFERENCES `players` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Friends system (safe to re-run)
CREATE TABLE IF NOT EXISTS `friends` (
  `player_id`  BIGINT UNSIGNED NOT NULL,
  `friend_id`  BIGINT UNSIGNED NOT NULL,
  `status`     ENUM('pending','accepted') NOT NULL DEFAULT 'pending',
  `created_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`player_id`, `friend_id`),
  KEY `friend_id` (`friend_id`),
  CONSTRAINT `friends_ibfk_1` FOREIGN KEY (`player_id`) REFERENCES `players` (`id`) ON DELETE CASCADE,
  CONSTRAINT `friends_ibfk_2` FOREIGN KEY (`friend_id`) REFERENCES `players` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
