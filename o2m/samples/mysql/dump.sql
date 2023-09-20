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
  `read_end` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Is last read gone to end ? (Boolean)',
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
  `data` varchar(92) DEFAULT '''''''''''''' COMMENT 'Concatenation of : spotify:playlist,artist,album,genre / podcast: or tunein:station or local:artist,album\r\nExamples : local:album:md5:e431c158da4fbb855da74cc68e2c845\r\nspotify:album:3gPOWmWT0q7Ygp95Xiuw1v\r\nm3u:iris.m3u8\r\npodcast+https://feed.pippa.io/public/shows/5b0030a',
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
('box_new_demo', 'mopidy_box', 0, 0, ' mopidy_box', NULL, 0, 1621086457, 'new_mopidy', NULL, NULL, 30, 3, '1181464119'),
('incoming_demo', 'Incoming', 1, 0, 'spotify:playlist:0zM5DUb7FYRVvVjBg3ULp3', NULL, 1, 1686824105, 'Incoming', 'shuffle', NULL, 15, 5, '1181464119'),
('favorites_demo', 'Favorites demo', 1, 0, 'spotify:playlist:4oXELBuV9B6QtxYwMdzsoE', '', 281, 1686472653, 'favorites', 'shuffle', 0, 30, 4, '1181464119'),
('last_info', 'Last infos', 1, 0, 'infos:library', ' ', 17, 1686826163, 'podcast', 'desc', NULL, 15, 3, '1181464119'),
('podcast_demo', 'Podcast demo', 1, 0, 'podcast+https://feeds.acast.com/public/shows/9851446c-d9b9-47a2-99a9-26d0a4968cc3', ' ', 6, 1686826210, 'podcast', 'shuffle', NULL, 150, 3, '1181464119'),
('radio_demo', 'Radio demo', 1, 0, 'tunein:station:s24875', '', 261, 1603522595, 'normal', '', 0, NULL, 5, '1181464119'),
('discover_demo', 'Discover demo', 1, 0, 'spotify:playlist:37i9dQZEVXcFRmKfy3mdyu', '', 5438, 1686827507, 'new', 'shuffle', 0, 30, 0, '1181464119'),
('recommandation_genre_demo', 'Reco genre jazz demo', 1, 0, 'spotify:recommendation:seeds:genres:french,jazz', '', 64, 1606308740, 'normal', '', 0, NULL, 5, 'lecok5'),
('recommandation_artist_demo', 'Reco artist justice demo', 1, 0, 'spotify:recommendation:seeds:artists:1gR0gsQYfi6joyO1dlp76N', ' 63MQldklfxkjYDoUE4T', 82, 1606577090, 'normal', '', 0, NULL, 5, 'lecok5'),
('playlist_demo', 'Playlist electro demo', 1, 0, 'spotify:playlist:0qBFSMuP85q8oDn8wRyegC', '', 710, 1686827783, 'normal', 'shuffle', 0, NULL, 6, '1181464119'),
('auto_demo', 'Auto', 1, 0, 'auto:library', NULL, 0, 1686401887, 'normal', 'shuffle', NULL, 50, 3, '1181464119');


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
