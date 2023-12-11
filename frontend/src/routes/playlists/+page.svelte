<script lang="ts">
  import { currentPlaylists } from "$lib/stores/store";
</script>
<section class="flex flex-col">
    {#each $currentPlaylists as playlist}
    <a href="/playlists/{playlist.uri}">{playlist.name}</a>
    {/each}

</section>