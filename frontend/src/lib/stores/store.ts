import { get, writable } from 'svelte/store';
export const modal = writable(false);
export const loginModal = writable(false);
import PocketBase from 'pocketbase';
import {PUBLIC_POCKETBASE_URL, PUBLIC_MOPIDY_WS_PORT} from '$env/static/public'
import type { Player, Playlist,Tracklist, User } from '../models/index';


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


const socket = new WebSocket(`ws://localhost:${PUBLIC_MOPIDY_WS_PORT}/mopidy/ws/`);

socket.addEventListener("open", () => {
    console.log("Opened");
    // get playlists
    let request = {"jsonrpc": "2.0", "id": 1, "method": "core.playlists.as_list"};
    socket.send(JSON.stringify(request));

    // get current get_current_tl_track
    request = {"jsonrpc": "2.0", "id": 2, "method": "core.playback.get_current_tl_track"};
    socket.send(JSON.stringify(request));

    // subscribe to currentPlaylistId
    currentPlaylistId.subscribe((currentPlaylistId) => {
        if (currentPlaylistId) {
            console.log("currentPlaylistId", currentPlaylistId);
            const request = {"jsonrpc": "2.0", "id": 2, "method": "core.playlists.lookup", "params": {"uri": currentPlaylistId}};
            socket.send(JSON.stringify(request));            
        }
    });

    // get playback state
    request = {"jsonrpc": "2.0", "id": 3, "method": "core.playback.get_state"};
    socket.send(JSON.stringify(request));

    // subscribe to player.state and set the playback state
    player.subscribe((player) => {
        if (player.state) {
            console.log("player.state", player.state);
            if (player.state == "playing") {
                console.log("▶️ player.state", player.state);
                const request = {"jsonrpc": "2.0", "id": 4, "method": "core.playback.play"};
                socket.send(JSON.stringify(request));
            }
            if (player.state == "paused") {
                console.log("▶️ player.state", player.state);
                const request = {"jsonrpc": "2.0", "id": 4, "method": "core.playback.pause"};
                socket.send(JSON.stringify(request));
            }
            if (player.state == "stopped") {
                console.log("▶️ player.state", player.state);
                const request = {"jsonrpc": "2.0", "id": 4, "method": "core.playback.stop"};
                socket.send(JSON.stringify(request));
            }

            //const request = {"jsonrpc": "2.0", "id": 4, "method": "core.playback.set_state", "params": {"new_state": player.state}};
            //socket.send(JSON.stringify(request));
        }
        if (player.track) {
            console.log("player.track", player.track);
            const request = {"jsonrpc": "2.0", "id": 5, "method": "core.tracklist.add", "params": {"uris": [player.track.uri]}};
            socket.send(JSON.stringify(request));
        }
    });

    // subscribe to tracklist and set the tracklist
    tracklist.subscribe((tracklist) => {
        if (tracklist) {
            console.log("tracklist", tracklist);
            //const request = {"jsonrpc": "2.0", "id": 6, "method": "core.playback.play", "params": {"tlid": tracklist[0].tlid}};
            //socket.send(JSON.stringify(request));
        }
    });

    
  });
  socket.addEventListener("message", (event) => {
    //console.log("Received response:", event.data);
    const response = JSON.parse(event.data);
    if (response.result) {
        // response.id 1 is the playlists list
        if (response.id == 1) {
            currentPlaylists.set(response.result);
        }
        // response.id 2 is the playlist
        if (response.id == 2) {
            console.log("currentPlaylist", response.result);
            currentPlaylist.set(response.result.tracks);
        }
        // response.id 3 is the playback state
        if (response.id == 3) {
            console.log("Player state", response);
            player.set({state: response.result});
        }
        // response.id 4 is the playback state
        if (response.id == 4) {
            console.log("Player state", response);
            player.set({state: response.result});
        }
        // response.id 5 is the tracklist add
        if (response.id == 5) {
            console.log("Tracklist add", response);
            // set the tracklist
            tracklist.set(response.result);
            // get player state
            const request = {"jsonrpc": "2.0", "id": 3, "method": "core.playback.get_state"};
          
        }
        if (response.id == 6) {

            const playlistUri = Object.keys(response?.result)[0];
            const image = response.result[playlistUri][0]?.uri;

            currentPlaylistsImages.update((currentPlaylistsImages) => {
                currentPlaylistsImages[playlistUri] = image;
                return currentPlaylistsImages;
            });
        }
        else{
            console.log("Uknown response id", response);
        }
    }

  });
  socket.addEventListener("error", (event) => {
  console.error("WebSocket error:", event);
  socket.close();
});


export function getPlaylistsImage(playlistUri: string) {
    const request = {"jsonrpc": "2.0", "id": 6, "method": "core.library.get_images", "params": {"uris": [playlistUri]}};
    socket.send(JSON.stringify(request));
}


