<script lang="ts">
  import "../app.css";
  import { onMount } from "svelte";
  import { watchUserChange, player, tracklist } from "$lib/stores/store";
  import Nav from "$lib/components/Nav.svelte";
  import Player from "$lib/components/Player.svelte";
  
  // DEBUG watch player, tracklist
  $: console.log("### Tracklist ###", $tracklist);
  $: console.log("### Player ###", $player);

  </script>
  <div class="flex">
    <slot />
  </div>
  <Player/>
  <Nav/>


