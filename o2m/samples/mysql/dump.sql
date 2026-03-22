-- ============================================================
--  O2M – Schéma complet (installation fraîche)
--  Server version: MariaDB / MySQL
--  Usage : mysql -u <user> -p <db_name> < dump.sql
-- ============================================================

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET NAMES utf8mb4;
SET time_zone = "+00:00";

-- ============================================================
--  TABLE `box`
-- ============================================================

CREATE TABLE IF NOT EXISTS `box` (
  `uid`                  varchar(30)   DEFAULT NULL,
  `description`          varchar(255)  DEFAULT NULL,
  `favorite`             tinyint(1)    NOT NULL DEFAULT 0   COMMENT 'Bool (is the box pinned or not)',
  `public`               tinyint(1)    NOT NULL DEFAULT 0   COMMENT 'Bool (is the content shared or not)',
  `data`                 text          DEFAULT ''           COMMENT 'Media URI(s) — spotify:*, podcast+https://, tunein:, local:, m3u:, auto:, o2m:…',
  `data_alt`             text          DEFAULT NULL,
  `read_count`           smallint(6)   DEFAULT NULL,
  `last_read_date`       bigint(20)    DEFAULT NULL,
  `option_type`          varchar(16)   DEFAULT 'normal'     COMMENT 'normal | new | favorites | hidden | trash | podcast | info | incoming',
  `option_sort`          varchar(16)   DEFAULT NULL         COMMENT 'shuffle | asc | desc',
  `option_duration`      int(16)       DEFAULT NULL         COMMENT 'max duration in seconds',
  `option_max_results`   int(16)       DEFAULT NULL         COMMENT 'max tracks to return',
  `option_discover_level` int(16)      DEFAULT 5            COMMENT '0-10',
  `user`                 varchar(16)   DEFAULT NULL,
  UNIQUE KEY `uid` (`uid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  TABLE `track`  (ex-stats)
-- ============================================================

CREATE TABLE IF NOT EXISTS `track` (
  `uri`              varchar(255)  NOT NULL                   COMMENT 'Unique Spotify / local / podcast URI',
  -- Playback statistics
  `last_read_date`   bigint(20)    DEFAULT NULL,
  `read_position`    int(11)       NOT NULL DEFAULT 0         COMMENT 'Last playback position (ms)',
  `read_end`         float         NOT NULL DEFAULT 0.5       COMMENT 'Average completion rate (0-1)',
  `read_count`       int(11)       NOT NULL DEFAULT 0,
  `read_count_end`   int(11)       NOT NULL DEFAULT 0,
  `skipped_count`    int(11)       NOT NULL DEFAULT 0,
  `in_library`       text          DEFAULT NULL               COMMENT 'Container URI if track is in library',
  `day_time_average` tinyint(2)    DEFAULT NULL               COMMENT 'Average hour of play (1-24)',
  `option_type`      varchar(16)   NOT NULL DEFAULT 'new'     COMMENT 'new | normal | favorites | hidden | trash | podcast | info | incoming',
  `username`         varchar(255)  DEFAULT NULL,
  -- Spotify metadata cache
  `name`             text          DEFAULT NULL               COMMENT 'Track title',
  `duration_ms`      int(11)       DEFAULT NULL,
  `track_number`     int(11)       DEFAULT NULL,
  `album_id`         varchar(255)  DEFAULT NULL               COMMENT '→ album.id',
  `preview_url`      text          DEFAULT NULL,
  `cached_at`        bigint(20)    DEFAULT NULL               COMMENT 'Cache timestamp (UTC)',
  `storage`          varchar(10)   NOT NULL DEFAULT 'sp'      COMMENT 'sp | local',
  `liked`            tinyint(1)    NOT NULL DEFAULT 0         COMMENT '1 = dans les tracks likés',
  `liked_at`         bigint(20)    DEFAULT NULL               COMMENT 'Date du like (UTC)',
  PRIMARY KEY (`uri`),
  UNIQUE KEY `uq_track_uri` (`uri`),
  KEY `idx_track_album_id`  (`album_id`),
  KEY `idx_track_cached_at` (`cached_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  TABLE `stats_raw`
-- ============================================================

CREATE TABLE IF NOT EXISTS `stats_raw` (
  `id`        int(11)       NOT NULL AUTO_INCREMENT,
  `read_date` bigint(20)    NOT NULL,
  `uri`       varchar(255)  NOT NULL,
  `read_hour` tinyint(2)    NOT NULL,
  `username`  varchar(255)  DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_raw_read_date` (`read_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  TABLE `album`
-- ============================================================

CREATE TABLE IF NOT EXISTS `album` (
  `id`           varchar(255)  NOT NULL                    COMMENT 'Spotify album ID',
  `uri`          varchar(255)  DEFAULT NULL                COMMENT 'spotify:album:ID',
  `name`         text          DEFAULT NULL,
  `artist_name`  text          DEFAULT NULL               COMMENT 'Artiste principal (dénormalisé)',
  `album_type`   varchar(32)   DEFAULT NULL                COMMENT 'album | single | compilation',
  `release_date` varchar(16)   DEFAULT NULL                COMMENT 'YYYY, YYYY-MM or YYYY-MM-DD',
  `total_tracks` int(11)       DEFAULT NULL,
  `image_url`    text          DEFAULT NULL,
  `storage`      varchar(10)   NOT NULL DEFAULT 'sp'       COMMENT 'sp | local',
  `cached_at`    bigint(20)    DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_album_cached_at` (`cached_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  TABLE `artist`
-- ============================================================

CREATE TABLE IF NOT EXISTS `artist` (
  `id`         varchar(255)  NOT NULL                      COMMENT 'Spotify artist ID',
  `uri`        varchar(255)  DEFAULT NULL                  COMMENT 'spotify:artist:ID',
  `name`       text          DEFAULT NULL,
  `popularity` int(11)       DEFAULT NULL                  COMMENT '0-100',
  `followers`  int(11)       DEFAULT NULL,
  `image_url`  text          DEFAULT NULL,
  `storage`    varchar(10)   NOT NULL DEFAULT 'sp'         COMMENT 'sp | local',
  `cached_at`  bigint(20)    DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_artist_cached_at` (`cached_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  TABLE `genre`
-- ============================================================

CREATE TABLE IF NOT EXISTS `genre` (
  `id`   int(11)       NOT NULL AUTO_INCREMENT,
  `name` varchar(255)  NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_genre_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  TABLE `playlist`
-- ============================================================

CREATE TABLE IF NOT EXISTS `playlist` (
  `id`           varchar(255)  NOT NULL                    COMMENT 'Spotify playlist ID',
  `uri`          varchar(255)  DEFAULT NULL                COMMENT 'spotify:playlist:ID',
  `name`         text          DEFAULT NULL,
  `description`  text          DEFAULT NULL,
  `owner_id`     varchar(255)  DEFAULT NULL,
  `total_tracks` int(11)       DEFAULT NULL,
  `snapshot_id`  varchar(255)  DEFAULT NULL                COMMENT 'Pour détecter les changements Spotify',
  `image_url`    text          DEFAULT NULL,
  `storage`      varchar(10)   NOT NULL DEFAULT 'sp'       COMMENT 'sp | local',
  `cached_at`    bigint(20)    DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_playlist_cached_at` (`cached_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  TABLE `playlisttrack`  (playlist.id ↔ track.uri)
-- ============================================================

CREATE TABLE IF NOT EXISTS `playlisttrack` (
  `playlist_id`  varchar(255)  NOT NULL   COMMENT '→ playlist.id',
  `track_uri`    varchar(255)  NOT NULL   COMMENT '→ track.uri',
  `position`     int(11)       NOT NULL DEFAULT 0,
  `added_at`     bigint(20)    DEFAULT NULL                COMMENT 'Date d''ajout à la playlist (UTC)',
  PRIMARY KEY (`playlist_id`, `track_uri`),
  KEY `idx_pt_track` (`track_uri`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  TABLE `trackartist`  (track.uri ↔ artist.id)
-- ============================================================

CREATE TABLE IF NOT EXISTS `trackartist` (
  `track_uri`  varchar(255)  NOT NULL   COMMENT '→ track.uri',
  `artist_id`  varchar(255)  NOT NULL   COMMENT '→ artist.id',
  `position`   int(11)       NOT NULL DEFAULT 0  COMMENT '0 = artiste principal',
  PRIMARY KEY (`track_uri`, `artist_id`),
  KEY `idx_ta_artist` (`artist_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  TABLE `albumartist`  (album.id ↔ artist.id)
-- ============================================================

CREATE TABLE IF NOT EXISTS `albumartist` (
  `album_id`   varchar(255)  NOT NULL   COMMENT '→ album.id',
  `artist_id`  varchar(255)  NOT NULL   COMMENT '→ artist.id',
  `position`   int(11)       NOT NULL DEFAULT 0,
  PRIMARY KEY (`album_id`, `artist_id`),
  KEY `idx_aa_artist` (`artist_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  TABLE `artistgenre`  (artist.id ↔ genre.id)
-- ============================================================

CREATE TABLE IF NOT EXISTS `artistgenre` (
  `artist_id`  varchar(255)  NOT NULL   COMMENT '→ artist.id',
  `genre_id`   int(11)       NOT NULL   COMMENT '→ genre.id',
  PRIMARY KEY (`artist_id`, `genre_id`),
  KEY `idx_ag_genre` (`genre_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
--  Données de démonstration (`box`)
-- ============================================================

INSERT INTO `box` (`uid`, `description`, `favorite`, `public`, `data`, `data_alt`, `read_count`, `last_read_date`, `option_type`, `option_sort`, `option_duration`, `option_max_results`, `option_discover_level`, `user`) VALUES
('mopidy_box',              'mopidy_box',            0, 1, 'mopidy_box',                                                      NULL, 0,   1621086457, 'new_mopidy', NULL,      NULL, 30, 3, '1181464119'),
('trash_demo',              'Trash',                 0, 0, 'spotify:playlist:4CAjrciXNfqiDdr757UwBx',                         NULL, 0,   1608365810, 'trash',      NULL,      NULL, 15, 5, '1181464119'),
('albums_spotify',          'Auto albums',           1, 1, 'albums:spotify',                                                  '',   1,   1686401887, 'normal',     'asc',     NULL, 50, 5, '1181464119'),
('04AD43D2204B80',          'Auto',                  1, 1, 'auto:library\r\ninfos:library',                                   'spotify:playlist:7wkPrsy6n3ydZ3KxZhOtDU', 942, 1686401887, 'normal', 'shuffle', NULL, 50, 5, '1181464119'),
('discover_demo',           'C1 Nouveautés',         1, 0, 'newnotcompleted:library\r\nspotify:playlist:2YndOajMlJlkj7x6WyevW6', NULL, 0, 1621086457, 'new_mopidy', NULL, NULL, 30, 3, '1181464119'),
('incoming_demo',           'C2 Incoming',           1, 0, 'spotify:playlist:0zM5DUb7FYRVvVjBg3ULp3',                         NULL, 1,   1686824105, 'incoming',   'shuffle', NULL, 15, 5, '1181464119'),
('favorites_demo',          'C3 Favorites',          1, 0, 'spotify:playlist:4oXELBuV9B6QtxYwMdzsoE',                         '',   281, 1686472653, 'favorites',  'shuffle', 0,   30, 4, '1181464119'),
('045340D2204B80',          'Radio France Inter',    1, 1, 'tunein:station:s24875',                                           '',   261, 1603522595, 'normal',     '',        0,   NULL, 5, '1181464119'),
('podcast_unfinished',      'Podcasts unfinished',   1, 0, 'podcasts:unfinished',                                             '',   171, 1682678797, 'podcast',    'asc',     0,   30, 5, '1181464119'),
('recommandation_genre_demo','Radio genre jazz',     1, 0, 'spotify:recommendation:seeds:genres:jazz',                        '',   64,  1606308740, 'normal',     '',        0,   NULL, 5, '1181464119');
