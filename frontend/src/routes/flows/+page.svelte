<script lang="ts">
    import { Node, Svelvet, Minimap, Controls } from 'svelvet';
    import { Anchor } from 'svelvet';
    import type { Connections } from 'svelvet';

    let nodes = [
        {id: "meteo", name: "Meteo", connections: ["meteo", "meteo_val"], outputs: 1, inputs: 1, x: 10, y: 40 },
    ]

  </script>
  
  <Svelvet id="my-canvas" height="{600}" TD minimap >
    {#each nodes as node }
        <Node 
            id={node.id} 
            label={node.name} 
            connections={["meteo", "meteo_val"]} 
            LR={true} 
            outputs={1}  
            position={{x:node.x, y:node.y}}
            on:nodeClicked={(e) => {console.log(node)} }
        />
    {/each}

    <Controls />
  </Svelvet>