<script lang="ts">
	import { page } from '$app/stores';
	import type { Box } from '$lib/models';
	import { currentUser } from '$lib/store';
	import { faPlay } from '@fortawesome/free-solid-svg-icons';
	import Fa from 'svelte-fa';
	const id = $page.params.id;
	$: console.log(id);
	let currentBox: Box;

	$: {
		if ($currentUser?.expand?.boxes) {
			currentBox = $currentUser.expand.boxes.find((box) => box.id === id);
		}
	}
</script>

<section>
	{#if currentBox}
		<!--Cover-->
		<div
			class="w-full h-full bg-center bg-cover bg-no-repeat h-72 flex flex-col justify-end"
			style="background-image: url(https://picsum.photos/seed/{currentBox.name}/1024/1024); "
		>
			<h2 class="p-4 text-5xl text-white">{currentBox.name}</h2>
		</div>
		<!--Action btn-->
		<div>
			<Fa icon={faPlay} class="text-5xl text-white" />
		</div>
	{:else}
		<h2>Box not found</h2>
	{/if}
</section>
