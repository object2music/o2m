import type { Box } from "$lib/models";
import { currentUser, pb } from "$lib/store";
import { get } from "svelte/store";

export async function createBox(box: Box) {
  const record = await pb.collection("boxes").create(box);
  await pb.collection("users").update(get(currentUser).id, {
    "boxes+": record.id,
});
  return record;
}