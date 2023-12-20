export interface Flow {
    id: string;
    name: string;
    duration: number;
    discover: number
    sort: "shuffle" | "desc" | "asc";
    max_results: number;
}