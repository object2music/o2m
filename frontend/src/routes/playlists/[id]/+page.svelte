<script lang="ts">
	import { page } from '$app/stores';
	import { currentPlaylists, currentPlaylistId, currentPlaylistsImages, player, tracklist } from '$lib/stores/store';
	import { onMount } from 'svelte';
	const playlistId: string = $page.params.id;

	console.log(playlistId);

	$currentPlaylistId = playlistId;

	$: {
		$currentPlaylist.forEach((playlist) => {
                getPlaylistsImage(playlist.uri);
            });
	}
</script>

<section>
	{#if $currentPlaylist}
		{#each $currentPlaylist as track}
			{#if $player?.track?.uri === track.uri}
				<div class="bg-primary">{track.name}</div>
                <a href={'/library/playlist/' + playlist.uri}>
					<div class="flex flex-col pl-2 pr-2 text-neutral-content rounded-3xl">
						<div class="flex items-center mb-4">
							<div class="w-14 mr-4">
								<img
									loading="lazy"
									src={$currentPlaylistsImages[playlist.uri]}
									class="rounded-xl"
								/>
							</div>
							<p>{playlist.name}</p>
						</div>
					</div>
				</a>
                
			{:else}
				<div on:click={() => ($player.track = track)}>{track.name}</div>
                <a href={'/library/playlist/' + playlist.uri}>
					<div class="flex flex-col pl-2 pr-2 text-neutral-content rounded-3xl">
						<div class="flex items-center mb-4">
							<div class="w-14 mr-4">
								<img
									loading="lazy"
									src={$currentPlaylistsImages[playlist.uri]}
									class="rounded-xl"
								/>
							</div>
							<p>{playlist.name}</p>
						</div>
					</div>
				</a>
			{/if}
		{/each}
	{/if}
</section>
