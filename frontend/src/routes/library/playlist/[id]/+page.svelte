<script lang="ts">
	import { page } from '$app/stores';
	import {
		player,
		currentPlaylist,
		currentPlaylistId,
		currentPlaylistsImages,
	} from '$lib/store';

	import {
		getPlaylistImage,
		setCurrentTrack 
	} from '$lib/utils/mopidy/requests';

	const playlistId: string = $page.params.id;
	$currentPlaylistId = playlistId;
	$: {
		if ($currentPlaylist) {
			console.log('currentPlaylist', $currentPlaylist);
			$currentPlaylist.forEach((track) => {
				getPlaylistImage(track.uri);
			});
		}
	}
</script>

<section>
	{#if $currentPlaylist}
		{#each $currentPlaylist as track}
			<a href={'/library/playlist/' + track.uri} on:click={() => setCurrentTrack(track.uri)}>
				<div class="flex flex-col pl-2 pr-2 text-neutral-content rounded-3xl">
					<div class="flex items-center mb-4">
						<div class="w-14 mr-4">
							<img loading="lazy" src={$currentPlaylistsImages[track.uri]} class="rounded-xl" />
						</div>
						<p>{track.name}</p>
					</div>
				</div>
			</a>
		{/each}
	{/if}
</section>
