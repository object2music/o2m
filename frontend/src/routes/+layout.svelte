<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { watchUserChange, player, tracklist } from '$lib/store';
	import Nav from '$lib/components/Nav.svelte';
	import Player from '$lib/components/Player.svelte';
	import { startWebsocket } from '$lib/utils/mopidy/websocket';

	// DEBUG watch player, tracklist
	$: console.log('### Tracklist ###', $tracklist);
	$: console.log('### Player ###', $player);

	onMount(() => {
		watchUserChange();
		startWebsocket();
	});
</script>

<div class="">
	<slot />
	<Player />
	<Nav />
</div>
