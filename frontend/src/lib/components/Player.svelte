<script lang="ts">
	import Fa from 'svelte-fa';
	import { faPlay, faPause } from '@fortawesome/free-solid-svg-icons';

	import {
		player,
		currentPlaylistsImages,
	} from '$lib/store';
	import {
		setPlayerState,
		getPlaylistImage,

		getPlayerState

	} from '$lib/utils/mopidy/requests';
	import { onMount } from 'svelte';
	import SnapStream from '$lib/utils/snapstream';

	let audio;
	let snapStream;
	let playerIcon = $player.state === 'playing' ? faPlay : faPause;

	$: console.log("### Player ###", $player);

	onMount(() => {
		console.log('mounted');
		console.log(player);
		if ($player.state === 'playing') {
			console.log('playing');
			$player.state = 'paused';
			playerIcon = faPause;
		}
		setInterval(() => {
			//getPlayerState();
		}, 2000);
	});

	$: {
		if ($player?.tracklist[0]?.track?.name) {
			console.log($player?.tracklist[0].track.name);
			getPlaylistImage($player?.tracklist[0].track.uri);
			switch ($player?.state) {
				case 'stopped':
					playerIcon = faPlay;
					break;
				case 'paused':
					playerIcon = faPlay;
					break;
				case 'playing':
					playerIcon = faPause;
					break;
			}
		}

	}

	function switchPlayerState(state){
		if(!snapStream) {
			snapStream = new SnapStream('ws://localhost:1780')

			audio.play().then(() => {
				snapStream.play();
			});
		}
		switch (state) {
			case 'stopped':
				$player.state = 'playing';
				playerIcon = faPause;
				break;
			case 'paused':
				$player.state = 'playing';
				playerIcon = faPause;
				break;
			case 'playing':
				$player.state = 'paused';
				playerIcon = faPlay;
				break;
		}
	}


</script>

<section class="fixed bottom-10 bg-neutral-content text-neutral w-full h-15">
	<audio class="hidden" controls loop bind:this={audio}>
		<source
			src="https://raw.githubusercontent.com/anars/blank-audio/master/10-seconds-of-silence.mp3"
			type="audio/mpeg"
		/>
		Your browser does not support the audio element.
	</audio>
	<div class="flex items-center h-12 justify-between">
		<div class="flex items-center">
			{#if $player?.tracklist[0]?.track?.uri}
				<div
					class="bg-contain bg-center bg-no-repeat w-10 h-8"
					style="background-image: url('{$currentPlaylistsImages[$player?.tracklist[0].track.uri]}')"
				/>
			{:else}
				<div
					class="bg-contain bg-center bg-no-repeat w-10 h-8"
					style="background-image: url('https://placekitten.com/512/512')"
				/>
			{/if}

			<div>
				<div class="text-sm">
					{#if $player?.tracklist[0]?.track?.name}
						{$player?.tracklist[0]?.track.name}
					{:else}
						Unknown Album
					{/if}
				</div>
				<div class="text-sm">
					{#if $player?.tracklist[0]?.track?.artists}
						{#each $player?.tracklist[0]?.track.artists as artist}
							{artist.name}
						{/each}
					{:else}
						Unknown Artist
					{/if}
				</div>
			</div>
		</div>

		<div class="mr-6" on:click={switchPlayerState($player?.state)}>
			<Fa icon={playerIcon} />
		</div>
	</div>

	<!-- {#if $player}
        <button on:click={() => $player.state = returnPlayerState($player.state)}>{ $player.state }</button>
    {/if} -->
</section>
