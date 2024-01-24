import { get, writable } from 'svelte/store';
export const modal = writable(false);
export const loginModal = writable(false);
import PocketBase from 'pocketbase';
import {PUBLIC_POCKETBASE_URL} from '$env/static/public'
import type { Player, Playlist,Tracklist, User } from './models/index';


export const pb = new PocketBase(PUBLIC_POCKETBASE_URL);

export const currentUser = writable(pb.authStore.model as User);
export const currentPlaylists = writable(<Playlist[]>[]);
export const currentPlaylistsImages = writable(<Record<string,string>>{});

export const currentPlaylist = writable([]);
export const currentPlaylistImages = writable(<Record<string,string>>{});
export const currentPlaylistId = writable("");
export let player = writable(<Player>{});
export let tracklist = writable(<Tracklist[]>[]);

let userSub = null;


pb.authStore.onChange(() => {
    currentUser.set(pb.authStore.model);
    watchUserChange();
});



export async function watchUserChange() {
    try {
        if(userSub){
            userSub()
        }
        const getUser = await pb.collection("users").getOne(get(currentUser).id, {expand: "boxes,stats"});
        currentUser.set(getUser);
        const currentUserId = get(currentUser).id
        if (get(currentUser).id) {
            // subscribe to the user data
            pb.collection("users").subscribe(get(currentUser).id, async ({action,  record}) => {
                if (action === "update") {
                    const getUser = await pb.collection("users").getOne(get(currentUser).id, {expand: "boxes,stats"});
                    console.log("user updated");
                    currentUser.set(getUser);

                }
            });
            userSub = () => {
                pb.collection("users").unsubscribe(currentUserId)
            }
        }
        
    }
    catch (e) {
        console.log("No user found");
    }
}




