<script>
    import Fa from 'svelte-fa'
    import { faHome, faMusic, faCircleNodes } from '@fortawesome/free-solid-svg-icons'

</script>
<section class="fixed bottom-0 bg-neutral h-10 w-full">
    <nav>
        <ul class="flex justify-around items-center h-10">
            <li>
                <a href="/">
                    <Fa icon={faHome} />
                </a>
            </li>
            <li>
                <a href="/nodes">
                    <Fa icon={faCircleNodes} />
                </a>
            </li>
            <li>
                <a href="/playlists">
                    <Fa icon={faMusic} />
                </a>
            </li>
        </ul>
    </nav>
</section>