import type { Flow } from "./Flow";

export interface Stat {
    id: string;
    uri: string;
    last_read_date: string;
    read_position: number;
    finished_score: number;
    count_score: number;
    skipped_score: number;
    day_time_average: number;
    flow: string[];
    created: string;
    updated: string;
    expand: {
        flow: Flow[];
    };
}