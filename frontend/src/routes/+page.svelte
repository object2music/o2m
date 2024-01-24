<script lang="ts">
	import { currentUser } from "$lib/stores/store";
    import { login, logout } from "$lib/utils/auth";

    let email = "";
    let password = "";

</script>
<section class="w-full">

    {#if $currentUser}
        <h1>Logged in as {$currentUser.name}</h1>
        <button on:click={logout}>Logout</button>
        <div class="p-4">
            <div class="flex p-4 items-center h-28 bg-cover rounded-sm" style="background-image: url('https://placekitten.com/1280/720')">
            <p class="uppercase text-white text-xl font-extrabold">Reprendre dernière écoute</p>
            </div>
            <p>Boites favorites</p>
            <div class="flex flex-wrap justify-around">
                <div class="w-2/5 flex p-4 items-center h-36 bg-cover rounded-sm" style="background-image: url('https://placekitten.com/512/512')">
                    <p class="uppercase text-white text-xl font-extrabold">Boite X</p>
                </div>
                <div class="w-2/5 flex p-4 items-center h-36 bg-cover rounded-sm" style="background-image: url('https://placekitten.com/512/512')">
                    <p class="uppercase text-white text-xl font-extrabold">Boite X</p>
                </div>
                <div class="w-2/5 flex p-4 items-center h-36 bg-cover rounded-sm" style="background-image: url('https://placekitten.com/512/512')">
                    <p class="uppercase text-white text-xl font-extrabold">Boite X</p>
                </div>
                <div class="w-2/5 flex p-4 items-center h-36 bg-cover rounded-sm" style="background-image: url('https://placekitten.com/512/512')">
                    <p class="uppercase text-white text-xl font-extrabold">Boite X</p>
                </div>

            </div>
            
        </div>

    {/if}
    {#if !$currentUser}
        <h1>Not logged in</h1>
        <!--Disable form redirect-->
        <form on:submit|preventDefault>
            <h1>Connexion</h1>
            <div class="form-control w-full max-w-xs">
                <!-- svelte-ignore a11y-label-has-associated-control -->
                <input type="text" placeholder="Votre Email" class="input input-bordered w-full max-w-xs" bind:value={email} />
                <input type="password" placeholder="Mot de passe" class="input input-bordered w-full max-w-xs" bind:value={password} />
                <button type="submit" class="btn btn-primary" on:click={login(email,password)} >Se connecter</button>
            </div>
        </form>
    {/if}


</section>