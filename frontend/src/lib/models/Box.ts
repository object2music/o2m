import type { Content } from "./Content";
import type { Flow } from "./Flow";

export interface Box {
    id?: string;
    name?: string;
    image?: string;
    favorite?: boolean;
    public?: boolean;
    contents?: string[];
    read_count?: number;
    last_read_date?: string;
    flow?: string;
    created?: string;
    updated?: string;
    expand?: {
        contents: Content[];
        flow: Flow;
    }
}