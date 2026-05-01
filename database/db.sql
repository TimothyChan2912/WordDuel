-- MySQL dump — WordDuel full schema
-- Run this to create/recreate the database from scratch

CREATE DATABASE IF NOT EXISTS `WordDuel`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `WordDuel`;

-- ─── players ─────────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS `friends`;
DROP TABLE IF EXISTS `daily_results`;
DROP TABLE IF EXISTS `match_results`;
DROP TABLE IF EXISTS `matches`;
DROP TABLE IF EXISTS `words`;
DROP TABLE IF EXISTS `players`;

CREATE TABLE `players` (
  `id`            BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
  `username`      VARCHAR(50)      NOT NULL,
  `email`         VARCHAR(100)     NOT NULL,
  `password_hash` VARCHAR(255)     NOT NULL,
  `elo`           INT UNSIGNED     NOT NULL DEFAULT 1000,
  `elo_timed`     INT UNSIGNED     NOT NULL DEFAULT 1000,
  `elo_streak`    INT UNSIGNED     NOT NULL DEFAULT 1000,
  `wins`          INT UNSIGNED     NOT NULL DEFAULT 0,
  `losses`        INT UNSIGNED     NOT NULL DEFAULT 0,
  `games_played`  INT UNSIGNED     NOT NULL DEFAULT 0,
  `skill_level`   ENUM('beginner','intermediate','advanced') NOT NULL DEFAULT 'beginner',
  `created_at`    TIMESTAMP(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email`    (`email`),
  KEY `idx_elo`        (`elo`),
  KEY `idx_elo_timed`  (`elo_timed`),
  KEY `idx_elo_streak` (`elo_streak`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── matches ─────────────────────────────────────────────────────────────────
CREATE TABLE `matches` (
  `id`           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `player1_id`   BIGINT UNSIGNED NOT NULL,
  `player2_id`   BIGINT UNSIGNED NOT NULL,
  `game_mode`    ENUM('classic','timed','streak') NOT NULL DEFAULT 'classic',
  `status`       ENUM('pending','active','completed') NOT NULL DEFAULT 'pending',
  `created_at`   TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `completed_at` TIMESTAMP(6) NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_player1_id` (`player1_id`),
  KEY `idx_player2_id` (`player2_id`),
  KEY `idx_status`     (`status`),
  CONSTRAINT `matches_ibfk_1` FOREIGN KEY (`player1_id`) REFERENCES `players` (`id`) ON DELETE CASCADE,
  CONSTRAINT `matches_ibfk_2` FOREIGN KEY (`player2_id`) REFERENCES `players` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── match_results ────────────────────────────────────────────────────────────
CREATE TABLE `match_results` (
  `id`             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `match_id`       BIGINT UNSIGNED NOT NULL,
  `winner_id`      BIGINT UNSIGNED DEFAULT NULL,
  `player1_score`  INT UNSIGNED    NOT NULL DEFAULT 0,
  `player2_score`  INT UNSIGNED    NOT NULL DEFAULT 0,
  `recorded_at`    TIMESTAMP(6)    NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `idx_match_id`  (`match_id`),
  KEY `idx_winner_id` (`winner_id`),
  CONSTRAINT `match_results_ibfk_1` FOREIGN KEY (`match_id`)  REFERENCES `matches` (`id`) ON DELETE CASCADE,
  CONSTRAINT `match_results_ibfk_2` FOREIGN KEY (`winner_id`) REFERENCES `players` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── friends ──────────────────────────────────────────────────────────────────
CREATE TABLE `friends` (
  `player_id` BIGINT UNSIGNED NOT NULL,
  `friend_id` BIGINT UNSIGNED NOT NULL,
  `status`    ENUM('pending','accepted') NOT NULL DEFAULT 'pending',
  `created_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`player_id`, `friend_id`),
  KEY `friend_id` (`friend_id`),
  CONSTRAINT `friends_ibfk_1` FOREIGN KEY (`player_id`) REFERENCES `players` (`id`) ON DELETE CASCADE,
  CONSTRAINT `friends_ibfk_2` FOREIGN KEY (`friend_id`) REFERENCES `players` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── daily_results ───────────────────────────────────────────────────────────
CREATE TABLE `daily_results` (
  `player_id`    BIGINT UNSIGNED NOT NULL,
  `date`         DATE            NOT NULL,
  `solved`       TINYINT(1)      NOT NULL DEFAULT 0,
  `guess_count`  TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `guesses`      VARCHAR(40)     NOT NULL DEFAULT '',
  `completed_at` TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`player_id`, `date`),
  KEY `idx_date` (`date`),
  CONSTRAINT `dr_fk_player` FOREIGN KEY (`player_id`) REFERENCES `players` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── words ───────────────────────────────────────────────────────────────────
CREATE TABLE `words` (
  `id`         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `word`       VARCHAR(255)    NOT NULL,
  `definition` TEXT,
  `difficulty` ENUM('easy','medium','hard') NOT NULL DEFAULT 'medium',
  `created_at` TIMESTAMP(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `word` (`word`),
  KEY `idx_difficulty` (`difficulty`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
