import type { Track } from "./Track";

export interface Player {
    volume?: number;
    mute?: boolean;
    time_position?: number;
    track?: Track;
    state?: "playing" | "paused" | "stopped";
}
