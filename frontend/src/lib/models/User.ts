import type { Box } from "./Box";
import type { Stat } from "./Stat";

export interface User {
    id: string;
    username: string;
    email: string;
    name: string;
    avatar: string;
    boxes: string[];
    stats: string;
    created: string;
    updated: string;
    expand: {
        boxes: Box[];
        stats: Stat[];
    }
}