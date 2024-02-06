import type { Track } from "./Track";

export interface Player {
    volume?: number;
    mute?: boolean;
    time_position?: number;
    tracklist: Track[];
    state?: "playing" | "paused" | "stopped";
}
