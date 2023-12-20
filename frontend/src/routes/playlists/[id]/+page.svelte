<script lang="ts">
    import { page } from '$app/stores';
    import { currentPlaylist, currentPlaylistId, player, tracklist } from '$lib/stores/store';
	import { onMount } from 'svelte';
    const playlistId : string = $page.params.id;

    $currentPlaylistId = playlistId;

    $: console.log($player);

</script>
<section>
    {#if $currentPlaylist}
        {#each $currentPlaylist as track}
        {#if $player?.track?.uri === track.uri}
            <div class="bg-primary">{track.name}</div>
        {:else}
            <div on:click={() => $player.track = track}>{track.name}</div>
        {/if}

        {/each}

    {/if}
</section>