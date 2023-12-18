<script lang="ts">
	import { faBox, faL, faMusic, faPlus, faSearch } from "@fortawesome/free-solid-svg-icons";
import Fa from "svelte-fa";

let items = [
    {
        name: 'Boxes',
    },
    {
        name: 'Playlist',
    },
    {
        name: 'Podcasts',
    },
    {
        name: 'Albums',
    },
    {
        name: 'Artists',
    },
    {
        name: 'Genres',
    }
]

let showBottomNav = false

</script>
<section>
    {#if showBottomNav}
        <div class="absolute w-full h-screen bg-black opacity-60" on:click={() => showBottomNav = false}></div>
    {/if}
    <div class="flex justify-between p-4 items-center">
        <div class="flex items-center">
            <div class="bg-neutral-content w-10 h-10 rounded-full mr-4"></div>
            <h1 class="text-2xl">Library</h1>
        </div>

        <div class="flex text-2xl">
            <div class="mr-4">
                <Fa icon={faSearch}  />
            </div>
            <div on:click={() => showBottomNav = true}>
                <Fa icon={faPlus}/> 
            </div>

        </div>
    </div>
    <div class="flex flex-row overflow-y-scroll pb-4">
        {#each items as item}
                    <button class="flex flex-col items-center justify-center pl-2 pr-2 bg-neutral text-neutral-content rounded-3xl ml-4">
                        <p>{item.name}</p>
                    </button>
        {/each}
    </div>

    <!-- Open the modal using ID.showModal() method -->
    <button class="btn" onclick="playlist_modal.showModal()">open modal</button>
    <dialog id="playlist_modal" class="modal">
    <div class="modal-box">
        <h3 class="font-bold text-lg">Create a new box</h3>
        <p class="py-4">Give your box a name </p>
    </div>
    <form method="dialog" class="modal-backdrop">
        <button>close</button>
    </form>
    </dialog>


    {#if showBottomNav == true}
        <div class="fixed bottom-0 z-10 bg-neutral rounded-t-xl pt-4 pl-4 pr-4 pb-8 text-white justify-center">
                <div onclick="playlist_modal.showModal()">
                    <div class="flex items-center">
                        <Fa icon={faBox} />
                        <h3 class="pl-1 text-xl">Box</h3>
                    </div>
                    <p class="text-sm"> Combine playslits podcats and more into your own recomandation system </p>
                </div>
            <div class="mt-4">
                <div class="flex items-center">
                    <Fa icon={faMusic} />
                    <h3 class="pl-1 text-xl">Playlist</h3>
                </div>
                <p class="text-sm">Create a simple playlist </p>
            </div>
        </div>
    {/if}
</section>