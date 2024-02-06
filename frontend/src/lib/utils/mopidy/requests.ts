import { get } from "svelte/store";
import { requestIds } from "./requestId";
import { socket } from "./websocket";

export function getPlaylists() {
    const request = {"jsonrpc": "2.0", "id": requestIds.getPlaylists, "method": "core.playlists.as_list"};
    socket.send(JSON.stringify(request));
}

export function getPlaylist(playlistUri: string) {
    const request = {"jsonrpc": "2.0", "id": requestIds.getPlaylist, "method": "core.playlists.lookup", "params": {"uri": playlistUri}};
    socket.send(JSON.stringify(request));
}

export function getTracklist() {
    const request = {"jsonrpc": "2.0", "id": requestIds.getTracklist, "method": "core.tracklist.get_tl_tracks"};
    socket.send(JSON.stringify(request));
}

export function getPlaybackState() {
    const request = {"jsonrpc": "2.0", "id": requestIds.getPlaybackState, "method": "core.playback.get_state"};
    socket.send(JSON.stringify(request));
}

export function clearTracklist() {
    const request = {"jsonrpc": "2.0", "id": requestIds.clearTracklist, "method": "core.tracklist.clear"};
    socket.send(JSON.stringify(request));
}

export function addTrackToTracklist(trackUri: string) {
    const request = {"jsonrpc": "2.0", "id": requestIds.addTrackToTracklist, "method": "core.tracklist.add", "params": {"uris": [trackUri]}};
    socket.send(JSON.stringify(request));
}

export async function setPlayerState(state: string) {
    console.log("setPlayerState", state);
    const request = {"jsonrpc": "2.0", "id": requestIds.setPlayerState, "method": `core.playback.${state}`};
    socket.send(JSON.stringify(request));
    getPlayerState();
}

export async function getPlayerTimePosition() {
    const request = {"jsonrpc": "2.0", "id": requestIds.getPlayerTimePosition, "method": "core.playback.get_time_position"};
    socket.send(JSON.stringify(request));
}

export function getCurrentTrack() {
    const request = {"jsonrpc": "2.0", "id": requestIds.getCurrentTrack, "method": "core.playback.get_current_track"};
    socket.send(JSON.stringify(request));
}


export function getVolume() {
    const request = {"jsonrpc": "2.0", "id": requestIds.getVolume, "method": "core.mixer.get_volume"};
    socket.send(JSON.stringify(request));
}


export function getPlaylistImage(playlistUri: string) {
    const request = {"jsonrpc": "2.0", "id": requestIds.getPlaylistImage, "method": "core.library.get_images", "params": {"uris": [playlistUri]}};
    socket.send(JSON.stringify(request));
}

export function  setCurrentTrack(trackUri: string) {
    clearTracklist();
    addTrackToTracklist(trackUri);
    setPlayerState("play");
    getPlayerState();
}

export function getPlayerState() {
    console.log("----------------getPlayerState-----------------");
    getPlaybackState();
    getTracklist();
    getVolume();
    getPlayerTimePosition();
}