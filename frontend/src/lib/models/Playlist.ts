export interface Playlist {
    name: string;
    type: "playlist" | "album" | "artist" | "directory" | "track";
}