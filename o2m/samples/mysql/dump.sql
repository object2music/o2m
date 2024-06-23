-- phpMyAdmin SQL Dump
-- version 5.0.2
-- https://www.phpmyadmin.net/
--
-- Host: localhost
-- Generation Time: Aug 04, 2023 at 04:50 PM
-- Server version: 10.6.14-MariaDB
-- PHP Version: 7.4.33

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `joan4181_o2m`
--

-- --------------------------------------------------------

--
-- Table structure for table `stats`
--

CREATE TABLE `stats` (
  `uri` varchar(255) NOT NULL,
  `last_read_date` bigint(20) NOT NULL,
  `read_position` int(11) NOT NULL DEFAULT 0 COMMENT 'Last read position',
  `read_end` decimal(10,0) NOT NULL DEFAULT 0 COMMENT 'Is last read gone to end ? (Boolean)',
  `read_count` tinyint(11) NOT NULL DEFAULT 0 COMMENT 'Count total read',
  `read_count_end` tinyint(11) NOT NULL DEFAULT 0 COMMENT 'Count total read to end',
  `skipped_count` tinyint(11) NOT NULL DEFAULT 0 COMMENT 'Count total skipped actions',
  `in_library` varchar(16) DEFAULT NULL COMMENT 'Is track in library ? If yes : uri cntainer value',
  `day_time_average` tinyint(2) DEFAULT NULL COMMENT 'Compute each read end day time average (1-24)',
  `option_type` varchar(16) NOT NULL,
  `username` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;

--
-- Dumping data for table `stats`
--

-- --------------------------------------------------------

--
-- Table structure for table `stats_raw`
--

CREATE TABLE `stats_raw` (
  `Id` int(11) NOT NULL,
  `read_date` bigint(20) NOT NULL,
  `uri` varchar(255) NOT NULL,
  `read_hour` tinyint(2) NOT NULL,
  `username` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;

--
-- Dumping data for table `stats_raw`
--

-- phpMyAdmin SQL Dump
-- version 5.0.2
-- https://www.phpmyadmin.net/
--
-- Host: localhost
-- Generation Time: Aug 27, 2023 at 10:57 AM
-- Server version: 10.6.15-MariaDB
-- PHP Version: 7.4.33

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `joan4181_o2m`
--

-- --------------------------------------------------------

--
-- Table structure for table `box`
--

CREATE TABLE `box` (
  `uid` varchar(30) DEFAULT NULL,
  `description` varchar(53) DEFAULT NULL,
  `favorite` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Bool (is the box pinned or not)',
  `public` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Bool (is the content shared or not)',
  `data` text COMMENT 'Concatenation of : spotify:playlist,artist,album,genre / podcast: or tunein:station or local:artist,album\r\nExamples : local:album:md5:e431c158da4fbb855da74cc68e2c845\r\nspotify:album:3gPOWmWT0q7Ygp95Xiuw1v\r\nm3u:iris.m3u8\r\npodcast+https://feed.pippa.io/public/shows/5b0030a',
  `data_alt` text DEFAULT NULL,
  `read_count` smallint(6) DEFAULT NULL,
  `last_read_date` bigint(20) DEFAULT NULL,
  `option_type` varchar(16) DEFAULT '''''''normal''''''' COMMENT 'option card type : normal (default), new (discover card:only play new tracks), favorites (preferred tracks), hidden (not considered by stats)',
  `option_sort` varchar(16) DEFAULT NULL COMMENT 'shuffle, desc, asc',
  `option_duration` int(16) DEFAULT NULL COMMENT 'max time in sec',
  `option_max_results` int(16) DEFAULT NULL COMMENT 'in tracks numbers',
  `option_discover_level` int(16) DEFAULT 5 COMMENT 'from 0-10',
  `user` varchar(16) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `box`
--

INSERT INTO `box` (`uid`, `description`, `favorite`, `public`, `data`, `data_alt`, `read_count`, `last_read_date`, `option_type`, `option_sort`, `option_duration`, `option_max_results`, `option_discover_level`, `user`) VALUES
('trash_demo', 'Trash', 0, 0, 'spotify:playlist:4CAjrciXNfqiDdr757UwBx', NULL, 0, 1608365810, 'Trash', NULL, NULL, 15, 5, '1181464119'),
('albums_spotify', 'Auto albums', 1, 1, 'albums:spotify', '', 1, 1686401887, 'normal', 'asc', NULL, 50, 5, '1181464119'),
('04AD43D2204B80', 'Auto', 1, 1, 'auto:library\r\ninfos:library', 'spotify:playlist:7wkPrsy6n3ydZ3KxZhOtDU', 942, 1686401887, 'normal', 'shuffle', NULL, 50, 5, '1181464119'),
('04B444D2204B80', 'Auto morning', 1, 0, 'auto:library\r\n\r\n#Politique\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_10217.xml?max_results=5\r\n\r\n#Geopolitique\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_10009.xml?max_results=5\r\n\r\n#Grand face à face\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_18378.xml\r\n\r\n#Chronique éco\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_18783.xml?max_results=5\r\n\r\n#revue de presse\r\npodcast+http://radiofrance-podcast.net/podcast09/rss_18780.xml?max_results=2\r\n\r\n#Par Jupiter\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_18153.xml?max_results=5\r\n\r\n#FC éco\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_10081.xml?max_results=50\r\n\r\n#710\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_10241.xml?max_results=5\r\n\r\n#Globa\r\npodcast+https://podcasts.files.bbci.co.uk/p02nq0gn.rss?max_results=2\r\n\r\npodcasts:unfinished\r\ntunein:station:s24875\r\ntunein:station:s2442\r\ntunein:station:s262540\r\n#tunein:station:s15200\r\n#infos:library', ' ', 0, 1684875843, 'info', 'shuffle', NULL, 30, 5, '1181464119'),
('discover_demo', 'C1 Nouveautés', 1, 0, 'newnotcompleted:library\r\nspotify:playlist:2YndOajMlJlkj7x6WyevW6\r\nspotify:playlist:37i9dQZEVXcFRmKfy3mdyu\r\nspotify:playlist:37i9dQZEVXbd8mSVuBhnSq\r\nspotify:playlist:6nOFgtda7DRWYgOUPjc2LX\r\nspotify:playlist:5RQz25zWdbmsGvDClilbkj\r\nspotify:playlist:1IhrDzE8Z4fegSvS8uHmJM', NULL, 0, 1621086457, 'new_mopidy', NULL, NULL, 30, 3, '1181464119'),
('incoming_demo', 'C2 Incoming', 1, 0, 'spotify:playlist:0zM5DUb7FYRVvVjBg3ULp3', NULL, 1, 1686824105, 'Incoming', 'shuffle', NULL, 15, 5, '1181464119'),
('favorites_demo', 'C3 Favorites', 1, 0, 'spotify:playlist:4oXELBuV9B6QtxYwMdzsoE', '', 281, 1686472653, 'favorites', 'shuffle', 0, 30, 4, '1181464119'),
('0446C5C90B0280', 'P Danse', 1, 0, 'spotify:playlist:0qBFSMuP85q8oDn8wRyegC', '', 11, 1602354874, 'normal', 'shuffle', NULL, 0, NULL, '1181464119'),
('04463DD2204B80', 'P Calm', 1, 0, 'spotify:playlist:4kXeq4DphjXBJVFNpBFl7c', 'm3u:Calm.m3u8', 473, 1686827607, 'normal', 'shuffle', NULL, 30, 4, '1181464119'),
('04CE6F193E2580', 'P Jazz', 1, 0, 'spotify:playlist:0CAZgc2rKvuU6uOxDupzEn', 'm3u:Jazz.m3u8', 710, 1686827783, 'normal', 'shuffle', 0, NULL, 6, '1181464119'),
('04CD41193E2580', 'Podcasts', 1, 0, '#sismique\r\npodcast+https://feeds.acast.com/public/shows/9851446c-d9b9-47a2-99a9-26d0a4968cc3?max_results=150\r\n#suite idées\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_16260.xml?max_results=50\r\n#code a changé\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_20856.xml?max_results=50\r\n#débat\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_18558.xml?max_results=50\r\n#Dixit\r\npodcast+https://anchor.fm/s/328b6334/podcast/rss?max_results=5\r\n#Youtube:Podcasts à écouter\r\nyt:https://www.youtube.com/playlist?list=PLM0sCcbvupIZ4spCcQB9DfhbVSluuEpFp\r\n#La planete bleue\r\npodcast+https://podcast.radiovostok.ch/laplanetebleue/feed.xml?max_results=5', '', 171, 1682678797, 'podcast', 'shuffle', 0, 100, 5, '1181464119'),
('podcast_unfinished', 'Podcasts unfinished', 1, 0, 'podcasts:unfinished', '', 171, 1682678797, 'podcast', 'asc', 0, 30, 5, '1181464119'),
('045340D2204B80', 'Radio France Inter', 1, 1, 'tunein:station:s24875', '', 261, 1603522595, 'normal', '', 0, NULL, 5, '1181464119'),
('infos_pv', 'Radio Infos', 1, 0, '#Politique\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_10217.xml?max_results=5\r\n\r\n#Geopolitique\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_10009.xml?max_results=5\r\n\r\n#Grand face à face\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_18378.xml\r\n\r\n#Chronique éco\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_18783.xml?max_results=5\r\n\r\n#revue de presse\r\npodcast+http://radiofrance-podcast.net/podcast09/rss_18780.xml?max_results=2\r\n\r\n#Par Jupiter\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_18153.xml?max_results=5\r\n\r\n#FC éco\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_10081.xml?max_results=5\r\n\r\n#710\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_10241.xml?max_results=5\r\n\r\n#Globa\r\npodcast+https://podcasts.files.bbci.co.uk/p02nq0gn.rss?max_results=2\r\n\r\n#Journal Tech\r\npodcast+https://radiofrance-podcast.net/podcast09/rss_24393.xml?max_results=20\r\n\r\npodcasts:unfinished\r\n#tunein:station:s15200\r\n#infos:library', '', 302, 1686827129, 'info', 'desc', NULL, 15, NULL, '1181464119'),
('last_info', 'Radio Infos last', 1, 1, 'infos:library', ' ', 17, 1686826163, 'info', 'desc', NULL, 15, 3, '1181464119'),
('recommandation_genre_demo', 'Radio genre jazz', 1, 0, 'spotify:recommendation:seeds:genres:jazz', '', 64, 1606308740, 'normal', '', 0, NULL, 5, '1181464119'),
('recommandation_artist_demo', 'Radio artist Massive attack', 1, 0, 'spotify:recommendation:seeds:artists:6FXMGgJwohJLUSr5nVlf9X', ' 63MQldklfxkjYDoUE4T', 82, 1606577090, 'normal', '', 0, NULL, 5, '1181464119');

--
-- Indexes for dumped tables
--

--
-- Indexes for table `stats`
--
ALTER TABLE `stats`
  ADD UNIQUE KEY `uri` (`uri`);

--
-- Indexes for table `stats_raw`
--
ALTER TABLE `stats_raw`
  ADD PRIMARY KEY (`Id`),
  ADD KEY `read_date` (`read_date`) USING BTREE;

--
-- Indexes for table `box`
--
ALTER TABLE `box`
  ADD UNIQUE KEY `uid` (`uid`);
COMMIT;

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `stats_raw`
--
ALTER TABLE `stats_raw`
  MODIFY `Id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
