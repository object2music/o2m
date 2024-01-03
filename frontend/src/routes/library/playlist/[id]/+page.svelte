<script lang="ts">
	import { page } from '$app/stores';
	import { currentPlaylist, currentPlaylistId, currentPlaylistsImages, getPlaylistsImage, player, tracklist } from '$lib/stores/store';
	import { onMount } from 'svelte';
	const playlistId: string = $page.params.id;

	console.log(playlistId);

	$currentPlaylistId = playlistId;

    $: console.log("currentPlaylistsImages",$currentPlaylistsImages);

	$: {
        if($currentPlaylist?.tracks){
            $currentPlaylist.tracks.forEach((track) => {
                getPlaylistsImage(track.uri);
            });
        }
	}
</script>

<section>
	{#if $currentPlaylist}
		{#each $currentPlaylist as track}
			{track.uri}
            {$currentPlaylistsImages[track.uri]}
		{/each}
	{/if}
</section>
