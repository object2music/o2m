<script lang="ts">
	import Fa from 'svelte-fa';
	import { faPlay, faPause } from '@fortawesome/free-solid-svg-icons';

	import { player } from '$lib/stores/store';
	import type { Player } from '$lib/models/player';
	import { onMount } from 'svelte';
	import SnapStream from '$lib/utils/snapstream';
	import SnapControl from '$lib/utils/snapcontrol';
	import Audiostream from '$lib/utils/snapstream';

	let audio;
	let snapStream;
    let playerIcon = $player.state === 'playing' ? faPause : faPlay;


    onMount(() => {
        console.log('mounted');
        console.log(player);
        if ($player.state === 'playing') {
            console.log('playing');
            $player.state = 'paused';
            playerIcon = faPause;
        }
    });

    $: console.log($player.state);

	function returnPlayerState(state) {
		// if state stopped, play if paused play if playing pause
		if (state === 'stopped') {
            console.log('will play');
            if (!snapStream) {
                snapStream = new SnapStream('ws://localhost:1780');
                snapStream.play();
            }
            $player.state = 'playing';
			playerIcon = faPlay;
		}
		if (state === 'paused') {
            console.log('paused before will play');
            if (!snapStream) {
                snapStream = new SnapStream('ws://localhost:1780');
                snapStream.play();
            }
            $player.state = 'playing';
			playerIcon = faPlay;
		}
		if (state === 'playing') {
            console.log('will pause');
            $player.state = 'paused';

			playerIcon = faPause;
		}
	}
</script>

<section class="fixed bottom-10 bg-neutral-content text-neutral w-full h-15">
	<audio class="hidden" controls bind:this={audio}>
		<source
			src="https://raw.githubusercontent.com/anars/blank-audio/master/10-seconds-of-silence.mp3"
			type="audio/mpeg"
		/>
		Your browser does not support the audio element.
	</audio>
	<div class="flex items-center h-12 justify-between">
		<div class="flex items-center">
			<div
				class="bg-contain bg-center bg-no-repeat w-10 h-8"
				style="background-image: url('https://placekitten.com/512/512')"
			/>
			<div>
				<div class="text-sm">
                    {#if $player?.track?.name}
                        {$player.track.name}
                        {:else}
                            Unknown Album
                    {/if}
                        
                </div>
				<div class="text-sm">
                    {#if $player?.track?.artists}
                        {#each $player.track.artists as artist}
                            {artist.name}
                        {/each}
                        {:else}
                            Unknown Artist
                    {/if}
                    
                </div>
			</div>
		</div>

		<div class="mr-6" on:click={returnPlayerState($player.state)}>
			<Fa icon={playerIcon}/>
		</div>
	</div>
    
	<!-- {#if $player}
        <button on:click={() => $player.state = returnPlayerState($player.state)}>{ $player.state }</button>
    {/if} -->
</section>
