
import {PUBLIC_MOPIDY_WS_PORT} from '$env/static/public'
import { socketOpen, currentPlaylist, currentPlaylistId, tracklist, currentPlaylists, currentPlaylistsImages, player } from '$lib/store';
import { requestIds } from './requestId';
import { getPlaybackState, getPlaylist, getPlaylists, getTracklist } from './requests';


export const socket = new WebSocket(`ws://localhost:${PUBLIC_MOPIDY_WS_PORT}/mopidy/ws/`);

socket.addEventListener("open", () => {
    console.log("WebSocket connected");
    socketOpen.set(true);
    // get playlists
    getPlaylists();

    // subscribe to currentPlaylistId
    currentPlaylistId.subscribe((currentPlaylistId) => {
        if (currentPlaylistId) {
            getPlaylist(currentPlaylistId);          
        }
    });

    // get playback state
    getPlaybackState();
   

    // subscribe to tracklist and set the tracklist
    tracklist.subscribe((tracklist) => {
        if (tracklist) {
            console.log("tracklist", tracklist);
        }
    });

    
});
socket.addEventListener("message", (event) => {
    //console.log("Received response:", event.data);
    const response = JSON.parse(event.data);
    if (response.result) {
        switch (response.id) {
            case requestIds.getPlaylists:
                currentPlaylists.set(response.result);
                break;

            case requestIds.getPlaylist:
                console.log("currentPlaylist", response.result);
                currentPlaylist.set(response.result.tracks);
                break;

            case requestIds.getPlaybackState:
                console.log("#####################", response.result);
                if (typeof response.result === "string") {
                    console.log("player.state", response.result);
                    player.set({state: response.result});
                }
                if (typeof response.result === "number") {
                    player.set({time_position: response.result});
                }
                break;
            case requestIds.getTracklist:
                console.log("tracklist", response.result);
                tracklist.set(response.result);
                // get player state
                const request = {"jsonrpc": "2.0", "id": 3, "method": "core.playback.get_state"};
                break;

            case requestIds.getPlaylistImage:
                const playlistUri = Object.keys(response?.result)[0];
                const image = response.result[playlistUri][0]?.uri;
                currentPlaylistsImages.update((currentPlaylistsImages) => {
                    currentPlaylistsImages[playlistUri] = image;
                    return currentPlaylistsImages;
                });
                break;

            default:
                console.log("Unknown response id", response);
        }
    }
});

  socket.addEventListener("error", (event) => {
  console.error("WebSocket error:", event);
  socket.close();
});

export function startWebsocket(){
    console.log("startWebsocket");
    getPlaybackState();
    getTracklist();
}