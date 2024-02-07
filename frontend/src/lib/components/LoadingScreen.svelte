<script lang="ts">
    export let display = false;
    export let text = "Loading"
    $: console.log('### LoadingScreen ###', display);
</script>
<section>
{#if display}
    <div class="fixed top-0 left-0 w-full h-full bg-black bg-opacity-80 z-50 flex justify-center items-center">
        <div class="text-white text-2xl">{text} <span class="loading loading-dots loading-xs"></span></div>
    </div>
{/if}
</section>