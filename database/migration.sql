-- Run this against an existing WordDuel database to add new columns
ALTER TABLE `players`
  ADD COLUMN IF NOT EXISTS `elo`          INT UNSIGNED NOT NULL DEFAULT 1000,
  ADD COLUMN IF NOT EXISTS `wins`         INT UNSIGNED NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS `losses`       INT UNSIGNED NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS `games_played` INT UNSIGNED NOT NULL DEFAULT 0;

ALTER TABLE `matches`
  ADD COLUMN IF NOT EXISTS `game_mode` ENUM('classic','timed','streak') NOT NULL DEFAULT 'classic';

-- Add streak mode to existing installations (safe to re-run)
ALTER TABLE `matches`
  MODIFY COLUMN `game_mode` ENUM('classic','timed','streak') NOT NULL DEFAULT 'classic';

ALTER TABLE `match_results`
  ADD COLUMN IF NOT EXISTS `player1_score` INT UNSIGNED NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS `player2_score` INT UNSIGNED NOT NULL DEFAULT 0;

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
