-- ============================================================
--  O2M – Migration cache Spotify local  (idempotent)
--  Rejouable sans erreur sur une base déjà partiellement migrée.
--  Usage : coller dans phpMyAdmin → onglet SQL → Exécuter
--    ou :  mysql -u <user> -p <db_name> < migrate_cache.sql
-- ============================================================

SET NAMES utf8mb4;
SET time_zone = "+00:00";

-- ============================================================
--  Macro interne : ajoute une colonne seulement si absente
-- ============================================================
DROP PROCEDURE IF EXISTS _add_col;
DELIMITER $$
CREATE PROCEDURE _add_col(
    IN tbl  VARCHAR(64),
    IN col  VARCHAR(64),
    IN def  TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = tbl
          AND COLUMN_NAME  = col
    ) THEN
        SET @_sql = CONCAT('ALTER TABLE `', tbl, '` ADD COLUMN ', def);
        PREPARE _s FROM @_sql; EXECUTE _s; DEALLOCATE PREPARE _s;
    END IF;
END$$
DELIMITER ;

-- ============================================================
--  Macro interne : ajoute un index seulement si absent
-- ============================================================
DROP PROCEDURE IF EXISTS _add_idx;
DELIMITER $$
CREATE PROCEDURE _add_idx(
    IN tbl  VARCHAR(64),
    IN idx  VARCHAR(64),
    IN def  TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = tbl
          AND INDEX_NAME   = idx
    ) THEN
        SET @_sql = CONCAT('ALTER TABLE `', tbl, '` ADD INDEX ', def);
        PREPARE _s FROM @_sql; EXECUTE _s; DEALLOCATE PREPARE _s;
    END IF;
END$$
DELIMITER ;

-- ============================================================
--  0. RENOMMAGE `stats` → `track`  (ignoré si déjà fait)
-- ============================================================
SET @do_rename = (
    SELECT COUNT(*) FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'stats'
);
SET @sql = IF(@do_rename > 0,
    'RENAME TABLE `stats` TO `track`',
    'SELECT "stats already renamed" AS info');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ============================================================
--  1. NOUVELLES COLONNES sur `track`
-- ============================================================
CALL _add_col('track', 'name',         '`name`         TEXT         DEFAULT NULL    COMMENT "Titre du morceau"');
CALL _add_col('track', 'liked',        '`liked`        TINYINT(1)   NOT NULL DEFAULT 0 COMMENT "1 = dans les tracks liks"');
CALL _add_col('track', 'liked_at',     '`liked_at`     BIGINT(20)   DEFAULT NULL    COMMENT "Date du like (UTC)"');
CALL _add_col('track', 'duration_ms',  '`duration_ms`  INT(11)      DEFAULT NULL    COMMENT "Dure en ms"');
CALL _add_col('track', 'track_number', '`track_number` INT(11)      DEFAULT NULL    COMMENT "Numro dans lalbum"');
CALL _add_col('track', 'album_id',     '`album_id`     VARCHAR(255) DEFAULT NULL    COMMENT "Rfrence album.id"');
CALL _add_col('track', 'preview_url',  '`preview_url`  TEXT         DEFAULT NULL    COMMENT "URL preview 30s"');
CALL _add_col('track', 'cached_at',    '`cached_at`    BIGINT(20)   DEFAULT NULL    COMMENT "Timestamp cache (UTC)"');
CALL _add_col('track', 'storage',      '`storage`      VARCHAR(10)  NOT NULL DEFAULT "sp" COMMENT "sp | local"');

CALL _add_idx('track', 'idx_track_album_id',  '`idx_track_album_id`  (`album_id`)');
CALL _add_idx('track', 'idx_track_cached_at', '`idx_track_cached_at` (`cached_at`)');

-- ============================================================
--  2. NOUVELLE TABLE `album`
-- ============================================================
CREATE TABLE IF NOT EXISTS `album` (
  `id`           VARCHAR(255) NOT NULL   COMMENT 'Spotify album ID',
  `uri`          VARCHAR(255) DEFAULT NULL,
  `name`         TEXT         DEFAULT NULL,
  `artist_name`  TEXT         DEFAULT NULL COMMENT 'Nom de l''artiste principal (dénormalisé)',
  `album_type`   VARCHAR(32)  DEFAULT NULL COMMENT 'album | single | compilation',
  `release_date` VARCHAR(16)  DEFAULT NULL,
  `total_tracks` INT(11)      DEFAULT NULL,
  `image_url`    TEXT         DEFAULT NULL,
  `storage`      VARCHAR(10)  NOT NULL DEFAULT 'sp',
  `cached_at`    BIGINT(20)   DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_album_cached_at` (`cached_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Si la table album existe déjà, ajouter les colonnes absentes
CALL _add_col('album', 'artist_name', '`artist_name` TEXT DEFAULT NULL COMMENT "Artiste principal (dnormalis)"');
CALL _add_col('album', 'saved',       '`saved`       TINYINT(1) NOT NULL DEFAULT 0 COMMENT "1 = dans les albums sauvegards"');
CALL _add_col('album', 'saved_at',    '`saved_at`    BIGINT(20) DEFAULT NULL COMMENT "Date de sauvegarde (UTC)"');

-- ============================================================
--  3. NOUVELLE TABLE `artist`
-- ============================================================
CREATE TABLE IF NOT EXISTS `artist` (
  `id`         VARCHAR(255) NOT NULL   COMMENT 'Spotify artist ID',
  `uri`        VARCHAR(255) DEFAULT NULL,
  `name`       TEXT         DEFAULT NULL,
  `popularity` INT(11)      DEFAULT NULL COMMENT '0-100',
  `followers`  INT(11)      DEFAULT NULL,
  `image_url`  TEXT         DEFAULT NULL,
  `storage`    VARCHAR(10)  NOT NULL DEFAULT 'sp',
  `cached_at`  BIGINT(20)   DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_artist_cached_at` (`cached_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Si la table artist existe déjà, ajouter les colonnes absentes
CALL _add_col('artist', 'followed',    '`followed`    TINYINT(1) NOT NULL DEFAULT 0 COMMENT "1 = suivi par lutilisateur"');
CALL _add_col('artist', 'followed_at', '`followed_at` BIGINT(20) DEFAULT NULL COMMENT "Date du suivi (UTC)"');

-- ============================================================
--  4. NOUVELLE TABLE `genre`
-- ============================================================
CREATE TABLE IF NOT EXISTS `genre` (
  `id`   INT(11)      NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(255) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_genre_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  5. JOINTURE `trackartist`
-- ============================================================
CREATE TABLE IF NOT EXISTS `trackartist` (
  `track_uri`  VARCHAR(255) NOT NULL COMMENT '→ track.uri',
  `artist_id`  VARCHAR(255) NOT NULL COMMENT '→ artist.id',
  `position`   INT(11)      NOT NULL DEFAULT 0,
  PRIMARY KEY (`track_uri`, `artist_id`),
  KEY `idx_ta_artist` (`artist_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  6. JOINTURE `albumartist`
-- ============================================================
CREATE TABLE IF NOT EXISTS `albumartist` (
  `album_id`   VARCHAR(255) NOT NULL COMMENT '→ album.id',
  `artist_id`  VARCHAR(255) NOT NULL COMMENT '→ artist.id',
  `position`   INT(11)      NOT NULL DEFAULT 0,
  PRIMARY KEY (`album_id`, `artist_id`),
  KEY `idx_aa_artist` (`artist_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  7. JOINTURE `artistgenre`
-- ============================================================
CREATE TABLE IF NOT EXISTS `artistgenre` (
  `artist_id`  VARCHAR(255) NOT NULL COMMENT '→ artist.id',
  `genre_id`   INT(11)      NOT NULL COMMENT '→ genre.id',
  PRIMARY KEY (`artist_id`, `genre_id`),
  KEY `idx_ag_genre` (`genre_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  8. NOUVELLE TABLE `playlist`
-- ============================================================
CREATE TABLE IF NOT EXISTS `playlist` (
  `id`           VARCHAR(255) NOT NULL COMMENT 'Spotify playlist ID',
  `uri`          VARCHAR(255) DEFAULT NULL,
  `name`         TEXT         DEFAULT NULL,
  `description`  TEXT         DEFAULT NULL,
  `owner_id`     VARCHAR(255) DEFAULT NULL,
  `total_tracks` INT(11)      DEFAULT NULL,
  `snapshot_id`  VARCHAR(255) DEFAULT NULL COMMENT 'Pour détecter les changements',
  `image_url`    TEXT         DEFAULT NULL,
  `storage`      VARCHAR(10)  NOT NULL DEFAULT 'sp',
  `cached_at`    BIGINT(20)   DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_playlist_cached_at` (`cached_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  9. JOINTURE `playlisttrack`
-- ============================================================
CREATE TABLE IF NOT EXISTS `playlisttrack` (
  `playlist_id`  VARCHAR(255) NOT NULL COMMENT '→ playlist.id',
  `track_uri`    VARCHAR(255) NOT NULL COMMENT '→ track.uri',
  `position`     INT(11)      NOT NULL DEFAULT 0,
  `added_at`     BIGINT(20)   DEFAULT NULL,
  PRIMARY KEY (`playlist_id`, `track_uri`),
  KEY `idx_pt_track` (`track_uri`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  10. JOINTURE `albumtrack`
-- ============================================================
CREATE TABLE IF NOT EXISTS `albumtrack` (
  `album_id`   VARCHAR(255) NOT NULL COMMENT '→ album.id',
  `track_uri`  VARCHAR(255) NOT NULL COMMENT '→ track.uri',
  `position`   INT(11)      NOT NULL DEFAULT 0,
  PRIMARY KEY (`album_id`, `track_uri`),
  KEY `idx_at_track` (`track_uri`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  Nettoyage des procédures temporaires
-- ============================================================
DROP PROCEDURE IF EXISTS _add_col;
DROP PROCEDURE IF EXISTS _add_idx;

-- ============================================================
--  Fin de migration
-- ============================================================
