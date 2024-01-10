<script lang="ts">
	import type { Box } from '$lib/models';
	import {
		currentPlaylists,
		currentPlaylistsImages,
		currentUser,

		getPlaylistsImage

	} from '$lib/stores/store';
	import { createBox } from '$lib/utils/box';
	import { faBox, faL, faMusic, faPlus, faSearch } from '@fortawesome/free-solid-svg-icons';
	import Fa from 'svelte-fa';

	let items = [
		{
			name: 'Boxes'
		},
		{
			name: 'Playlist'
		},
		{
			name: 'Podcasts'
		},
		{
			name: 'Albums'
		},
		{
			name: 'Artists'
		},
		{
			name: 'Genres'
		}
	];

	let currentItem = 'Boxes';

	let box: Box = {
		name: ''
	};

	let showBottomNav = false;

	$: {
		$currentPlaylists.forEach((playlist) => {
                getPlaylistsImage(playlist.uri);
            });
	}
</script>

<section>
	{#if showBottomNav}
		<div
			class="absolute w-full h-screen bg-black opacity-60"
			on:click={() => (showBottomNav = false)}
		/>
	{/if}
	<div class="flex justify-between p-4 items-center">
		<div class="flex items-center">
			<div class="bg-neutral-content w-10 h-10 rounded-full mr-4" />
			<h1 class="text-2xl">Library</h1>
		</div>

		<div class="flex text-2xl">
			<div class="mr-4">
				<Fa icon={faSearch} />
			</div>
			<div on:click={() => (showBottomNav = true)}>
				<Fa icon={faPlus} />
			</div>
		</div>
	</div>
	<div class="flex flex-row overflow-y-scroll pb-4 mb-4">
		{#each items as item}
			<button
				class="flex flex-col items-center justify-center pl-2 pr-2 text-neutral-content rounded-3xl ml-4 {item.name ===
				currentItem
					? 'bg-neutral'
					: ''}"
				on:click={() => (currentItem = item.name)}
			>
				<p>{item.name}</p>
			</button>
		{/each}
	</div>
	<div>
		{#if currentItem === 'Boxes'}
			{#if $currentUser?.expand?.boxes}
				{#each $currentUser.expand.boxes as box}
					<a href={'/library/box/' + box.id}>
						<div class="flex flex-col pl-2 pr-2 text-neutral-content rounded-3xl">
							<div class="flex items-center mb-4">
								<div class="w-14 mr-4">
									<img
										src={'https://picsum.photos/seed/' + box.name + '/200/200'}
										class="rounded-xl"
									/>
								</div>
								<p>{box.name}</p>
							</div>
						</div>
					</a>
				{/each}
			{:else}
				<p class="text-center">You don't have any boxes yet</p>
			{/if}
		{/if}
		{#if currentItem === 'Playlist'}
			{#each $currentPlaylists as playlist}
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
			{/each}
		{/if}
	</div>

	<dialog id="playlist_modal" class="modal">
		<div class="modal-box">
			<h3 class="font-bold text-lg">Create a new box</h3>
			<p class="py-4">Give your box a name</p>
			<input
				type="text"
				class="input input-bordered"
				placeholder="Box name"
				bind:value={box.name}
			/>
			<form method="dialog" class="modal-backdrop">
				<div class="mt-4 flex justify-center">
					<button
						class="btn btn-primary"
						on:click={async () => {
							await createBox(box);
							showBottomNav = false;
						}}>Create</button
					>
				</div>
			</form>
		</div>
		<form method="dialog" class="modal-backdrop">
			<button>close</button>
		</form>
	</dialog>

	{#if showBottomNav == true}
		<div
			class="fixed bottom-0 z-10 bg-neutral rounded-t-xl pt-4 pl-4 pr-4 pb-8 text-white justify-center"
		>
			<div onclick="playlist_modal.showModal()">
				<div class="flex items-center">
					<Fa icon={faBox} />
					<h3 class="pl-1 text-xl">Box</h3>
				</div>
				<p class="text-sm">Combine playslits podcats and more into your own recomandation system</p>
			</div>
			<div class="mt-4">
				<div class="flex items-center">
					<Fa icon={faMusic} />
					<h3 class="pl-1 text-xl">Playlist</h3>
				</div>
				<p class="text-sm">Create a simple playlist</p>
			</div>
		</div>
	{/if}
</section>
