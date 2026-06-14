//  o2m.js and o2m.css should be inserted in the mopidy-iris extension
//  in /usr/local/lib/pythonx.x/dist-packages/mopidy_iris/static
//  and inserted in index.html 
//     <link rel="stylesheet" href="o2m.css">
//    <script type="text/javascript" src="o2m.js"></script>

window.onload = function() {
  setTimeout(() => {
  //------------------INIT--------------------- 
  
  list = document.getElementsByClassName('sidebar__menu')[0];
  //host = window.location.host;
  base_url = window.location.origin.split( '//' )[0]+'//'+window.location.origin.split( '//' )[1].split(':')[0];
  base_url += ':6681/api/'
  backoffice_uri = 'http://localhost:5011'
  //backoffice_uri += 'sql.php?table=box&sql_query=SELECT+%2A+FROM+%60box%60++%0AORDER+BY+%60box%60.%60favorite%60++DESC&session_max_rows=100&is_browse_distinct=0'
  //alert(base_url)

  // --- O2M status request scheduler (prevents browser resource exhaustion) ---
  // NOTE: Must live in the function scope (not inside a block), because update_o2m_status()
  // is called from multiple places and needs access to these.
  const O2M_STATUS_MAX_CONCURRENT = 4;
  const O2M_STATUS_CACHE_TTL_MS = 5 * 60 * 1000;
  const o2mStatusCache = new Map(); // uri -> { text, ts }
  const o2mStatusPending = new Set(); // uri currently queued/in-flight
  const o2mStatusQueue = []; // { el, uri, show }
  let o2mStatusInFlight = 0;

  function o2mStatusGetCached(uri) {
    const entry = o2mStatusCache.get(uri);
    if (!entry) return null;
    if ((Date.now() - entry.ts) > O2M_STATUS_CACHE_TTL_MS) {
      o2mStatusCache.delete(uri);
      return null;
    }
    return entry.text;
  }

  function o2mStatusApply(el, update_text, show) {
    try {
      if ((update_text.includes('podcast')) || (el.innerHTML.includes('podcast+'))){
        el.style.backgroundColor = "Gainsboro";
        update_text = update_text.replace("library","podcast");
      }
      else if (update_text.includes('library')){
        el.style.backgroundColor = "LightSkyBlue";
      }
      else if (update_text.includes('favorites')){
        el.style.backgroundColor = "YellowGreen";
      }
      else if (update_text.includes('incoming')){
        el.style.backgroundColor = "GoldenRod";
      }
      else if (update_text.includes('new')){
        el.style.backgroundColor = "orange";
      }
      else if (update_text.includes('trash')){
        el.style.backgroundColor = "FireBrick";
      }
      else if (update_text.includes('hidden')){
        el.style.backgroundColor = "IndianRed";
      }
      else if (update_text.includes('info')){
        el.style.backgroundColor = "Gainsboro";
      }

      el.innerHTML = update_text;
      if (!el.classList.contains('show')) el.classList.add('show');
      if (el.classList.contains('hide')) el.classList.remove('hide');
    } catch (e) {
      console.error('o2m_status apply error', e);
    }
  }

  function o2mStatusPump() {
    while (o2mStatusInFlight < O2M_STATUS_MAX_CONCURRENT && o2mStatusQueue.length > 0) {
      const job = o2mStatusQueue.shift();
      const uri = job && job.uri;
      const el = job && job.el;
      if (!uri || !el) {
        continue;
      }

      const cached = o2mStatusGetCached(uri);
      if (cached) {
        o2mStatusPending.delete(uri);
        o2mStatusApply(el, cached, job.show);
        continue;
      }

      o2mStatusInFlight += 1;
      const xhr10 = new XMLHttpRequest();
      xhr10.onreadystatechange = function() {
        if (xhr10.readyState === xhr10.DONE) {
          o2mStatusInFlight -= 1;
          o2mStatusPending.delete(uri);

          if (xhr10.status === 200) {
            const text = xhr10.responseText;
            o2mStatusCache.set(uri, { text, ts: Date.now() });
            o2mStatusApply(el, text, job.show);
          }

          o2mStatusPump();
        }
      };
      xhr10.open("GET", base_url + "track_status?uri=" + encodeURIComponent(uri));
      xhr10.send();
    }
  }
  
  //Listeners for DOM change in IRIS (o2m_status)
    //Node of lists tracks changing 
    const targetNode = document.querySelectorAll("section.list-wrapper")[0];
    if (targetNode && targetNode.nodeType){

      // Options for the observer (which mutations to observe)
      const config = {childList: true, subtree: true};
      flag_o2m_status = 0;

      // Callback function to execute when mutations are observed
      let o2mStatusDebounceTimer = null;
      const callback = (mutationList, observer) => {
        if (o2mStatusDebounceTimer) {
          clearTimeout(o2mStatusDebounceTimer);
        }
        o2mStatusDebounceTimer = setTimeout(() => {
          if (flag_o2m_status !== 0) return;
          flag_o2m_status = 1;
          try {
            const nodes = document.querySelectorAll(".o2m_status.hide");
            for (const el of nodes) {
              const uri1 = el.innerHTML;
              update_o2m_status(el, uri1);
            }
          } catch (e) {
            console.error(e);
          }
          flag_o2m_status = 0;
        }, 250);
      };

      // Create an observer instance linked to the callback function
      const observer = new MutationObserver(callback);
      observer.observe(targetNode, config);

    //Listeners for DOM change in IRIS (current-track__title)
      //Node of lists tracks changing 
      const targetNode1 = document.getElementById("o2m_status_current");

      // Options for the observer (which mutations to observe)
      try { 
        const config1 = {attributes: true, childList: true, subtree: true };

      // Callback function to execute when mutations are observed
        const callback1 = (mutationList1, observer1) => {
        for (const mutation1 of mutationList1) {
                  uri1 = mutation1.target.innerHTML;
                  update_o2m_status(mutation1.target,uri1,"all");
                } 
          };
        

      // Create an observer instance linked to the callback function
      const observer1 = new MutationObserver(callback1);
      observer1.observe(targetNode1, config1);
      }
      catch (error) {
        console.error(error);
      }
    }
    
  //----------------FUNCTIONS-------------

    function update_o2m_status(update,uri,show = "min"){
      if (!uri) return;

      // If the element already contains a rendered status, do nothing.
      const current = String(update.innerHTML || '');
      if (
        current.includes('library - ') ||
        current.includes('favorites - ') ||
        current.includes('incoming - ') ||
        current.includes('podcast - ') ||
        current.includes('info - ') ||
        current.includes('trash - ') ||
        current.includes('hidden - ') ||
        current.includes('normal - ') ||
        current.includes('new')
      ) {
        return;
      }

      // Avoid scheduling duplicate work for the same URI
      const cached = o2mStatusGetCached(uri);
      if (cached) {
        o2mStatusApply(update, cached, show);
        return;
      }
      if (o2mStatusPending.has(uri)) {
        return;
      }
      o2mStatusPending.add(uri);
      o2mStatusQueue.push({ el: update, uri: uri, show: show });
      o2mStatusPump();
    }

    function update_style_all_button() {
      //To be created if uids are saved in page attribute
    }

  function update_style_button_box(uid,b){
    var xhr0 = new XMLHttpRequest();
    xhr0.onreadystatechange = function() {
        if (xhr0.readyState == xhr0.DONE) {
            if (xhr0.status === 200) {
            if (xhr0.responseText=='1') {b.classList.add("sidebar__menu__item--active");}
            if (xhr0.responseText=='0') {b.classList.remove("sidebar__menu__item--active");}
        }}
    }
    xhr0.open("GET",base_url+"box_activated?uid="+uid);
    xhr0.send();
  }

  function create_button_box(uid,name){
    var b = document.createElement("button");
    b.innerHTML = "<i class=\"icon icon--material \">recent_actors</i>"+name;
    b.className = "sidebar__menu__item icon icon--material";
    b.onclick = function(){  
        var xhr = new XMLHttpRequest();
        xhr.open("GET",base_url+"box?uid="+uid+"&mode=toogle");
        xhr.send();
        setTimeout(() => {
          update_style_button_box(uid,b)
      },1000);
    };
  list.insertBefore(b, list.children[0]);
  update_style_button_box(uid,b)
  timerId = setInterval(() => update_style_button_box(uid,b), 600000);
  }

  //////////////////////////////////////////////////////////////////////////////////
  var b = document.createElement("div");
  b.innerHTML = "<br/>";      
  list.insertBefore(b, list.children[0]);

//BACKOFFICE
  var b9 = document.createElement("button");
  b9.innerHTML = "<i class=\"icon icon--material \">explore</i>Backoffice";
  b9.className = "sidebar__menu__item icon icon--material";
  b9.onclick = function(){
    window.open(backoffice_uri, '_blank');
  }
  list.insertBefore(b9, list.children[0]);

//SPOTIPY
  var xhr1 = new XMLHttpRequest();

  xhr1.onreadystatechange = function() {
      if (xhr1.readyState == xhr1.DONE) {
          if (xhr1.status === 200) {
          sp = xhr1.responseText;
          
          var b8 = document.createElement("button");
          b8.innerHTML = "<i class=\"icon icon--material \">explore</i>"+sp;
          b8.className = "sidebar__menu__item icon icon--material";
          b8.onclick = function(){ 
            window.open(base_url+sp, '_blank');
          }
          //list.insertBefore(b8, list.children[0]);
        }}};
  xhr1.open("GET",base_url+"spotipy_check");
  xhr1.send();

//RESET
  var bClear = document.createElement("button");
  bClear.innerHTML = "<i class=\"icon icon--material \">delete</i>Clear last hour";
  bClear.className = "sidebar__menu__item icon icon--material";
  bClear.onclick = function(){
    if (!confirm("Effacer l'historique de la dernière heure (stats_raw) ?")) return;
    var xhr = new XMLHttpRequest();
    xhr.open("GET", base_url+"clear_today_history");
    xhr.onload = function() {
      bClear.innerHTML = "<i class=\"icon icon--material \">delete</i>History cleared";
      setTimeout(() => { bClear.innerHTML = "<i class=\"icon icon--material \">delete</i>Clear last hour"; }, 3000);
    };
    xhr.send();
  };
  list.insertBefore(bClear, list.children[0]);

  var b4 = document.createElement("button");
  b4.innerHTML = "<i class=\"icon icon--material \">explore</i>Relaunch";
  b4.className = "sidebar__menu__item icon icon--material";
  b4.onclick = function(){
    var xhr = new XMLHttpRequest();
    xhr.open("GET", base_url+"restart_mopidy");
    xhr.send();
    b4.innerHTML = "<i class=\"icon icon--material \">explore</i>Restarting…";
    b4.disabled = true;
    setTimeout(() => {
      var but = document.getElementsByTagName('button');
      for(i = 0; i < but.length; i++) {but[i].classList.remove("sidebar__menu__item--active");}
    }, 500);
  };
  list.insertBefore(b4, list.children[0]);

//BOXES DISPLAY (From API)
  var xhr5 = new XMLHttpRequest();
  xhr5.onreadystatechange = function() {
      if (xhr5.readyState == xhr5.DONE) {
          if (xhr5.status === 200) {
          boxes = xhr5.responseText;
          const obj = JSON.parse(boxes).reverse();
          for(let i = 0; i < obj.length; i++) {
            create_button_box(obj[i].uid,obj[i].description);
          }
        }}};
  xhr5.open("GET",base_url+"box_favorites");
  xhr5.send();

  // O2M STATUS : STATUS DISPLAY Injection in IRIS (from API)
  function o2m_status_update(){
    const o2m_status = document.querySelectorAll(".o2m_status.hide").forEach(function(update) {
      try { 
        uri1 = update.innerHTML;
        update_o2m_status(update,uri1);
      } 
      catch (error) {
        console.error(error);
      }
  });
  }
  o2m_status_update();
  // One follow-up pass shortly after initial paint
  {setTimeout(() => {
    o2m_status_update();
  }, 1500);}

  /*
  for (let i = 0; i < 3; i++) {
  if (document.querySelectorAll(".o2m_status.hide").length>0)
  {setTimeout(() => {
    o2m_status_update();
  }, "10000");}
  }*/
  

  const o2m_status1 = document.getElementById("o2m_status_current");
  try { 
    uri1 = o2m_status1.innerHTML;
    update_o2m_status(o2m_status1,uri1,"all");
  } 
  catch (error) {
    console.error(error);
  }

//OpenLevel Input and value
  var xhr0 = new XMLHttpRequest();
  xhr0.onreadystatechange = function() {
      if (xhr0.readyState == xhr0.DONE) {
          if (xhr0.status === 200) {
          ol = xhr0.responseText;

          var b5 = document.createElement("input");
          b5.setAttribute("type", "range");
          b5.setAttribute("value", ol);
          b5.setAttribute("min", "0");  
          b5.setAttribute("max", "10");
          b5.onchange = function(){
            setTimeout(() => {
            var xhr = new XMLHttpRequest();
            xhr.open("GET",base_url+"dl_on?dl="+b5.value);
            xhr.send();
            },1000);
          };
          b5.addEventListener("wheel", function(e){
            if (e.deltaY < 0){
              slider.valueAsNumber += 1;
            }else{
              slider.value -= 1;
            }
            e.preventDefault();
            e.stopPropagation();
          })
      list.insertBefore(b5, list.children[0]);
      }}
  }
  xhr0.open("GET",base_url+"dl");
  xhr0.send();

  var slider = document.getElementsByClassName("slider__input");
  /*slider.addEventListener("wheel", function(e){
    if (e.deltaY < 0){
      slider.valueAsNumber += 1;
    }else{
      slider.value -= 1;
    }
    e.preventDefault();
    e.stopPropagation();
  })
*/

// Called from the tap overlay handler (user gesture context).
// 1. Unlocks Web Audio API: creating + resuming an AudioContext in a gesture
//    handler signals the browser to resume ALL suspended AudioContexts on the
//    page, including Iris's internal SnapStream ctx. This is why clicking the
//    expand button manually fixes the stream — it's just a user gesture.
// 2. Clicks the expand button so Iris re-renders OutputControl (reinforces gesture).
// 3. Auto-plays via Mopidy RPC if tracklist is not empty and not already playing.
function enableSnapcastAndPlay() {
  // Unlock Web Audio API for the whole page
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) {
      const tmp = new AC();
      tmp.resume().then(() => tmp.close()).catch(() => {});
    }
  } catch (e) {}

  // Click expand button to trigger Snapcast stream init, then close it automatically
  const expandBtn = document.querySelector('button.control.expanded-controls[data-qa-file="PlaybackControls"]');
  if (expandBtn) {
    expandBtn.click();
    console.log('o2m: clicked expand controls');
    setTimeout(() => {
      const btn = document.querySelector('button.control.expanded-controls[data-qa-file="PlaybackControls"]');
      if (btn) { btn.click(); console.log('o2m: closed expand controls'); }
    }, 1500);
  }

  // Auto-play: start playback if tracklist non-empty and not already playing
  const mopidyRpc = window.location.protocol + '//' + window.location.hostname + ':6680/mopidy/rpc';
  const rpc = (method) => fetch(mopidyRpc, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({jsonrpc: '2.0', id: 1, method, params: {}})
  }).then(r => r.json()).then(j => j.result);

  Promise.all([rpc('core.playback.get_state'), rpc('core.tracklist.get_length')])
    .then(([state, length]) => {
      console.log('o2m: state=' + state + ' length=' + length);
      if (state !== 'playing' && length > 0) {
        fetch(base_url + 'toogle_play')
          .then(() => console.log('o2m: playback started'))
          .catch(err => console.error('o2m: toogle_play error:', err));
      }
    })
    .catch(err => console.error('o2m: mopidy rpc error:', err));
}

// Mobile: show a tap overlay (satisfies browser user-gesture requirement for audio)
try {
  const isMobile = (window.matchMedia && window.matchMedia('(max-width: 768px)').matches)
                 || /Mobi|Android|iPhone|iPad|iPod/.test(navigator.userAgent);
  if (isMobile) {
    const overlay = document.createElement('div');
    overlay.id = 'o2m-audio-overlay';
    Object.assign(overlay.style, {
      position: 'fixed', top: '0', left: '0', right: '0', bottom: '0',
      background: 'rgba(0,0,0,0.75)', zIndex: '9999',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', cursor: 'pointer'
    });
    overlay.innerHTML = '<div style="color:white;font-size:40px;margin-bottom:12px">▶</div>'
                      + '<div style="color:white;font-size:18px;font-weight:bold">Tap to start audio</div>';
    overlay.addEventListener('click', () => {
      overlay.remove();
      enableSnapcastAndPlay();
    }); // , { once: true }
    document.body.appendChild(overlay);
  }
} catch (e) {
  console.error('o2m: mobile audio overlay error', e);
}

// Initialize playback on phone devices only (one-time on load).
// Téléphone uniquement : pas d'alimentation auto (resume + lancement de box/tag)
// sur desktop ni tablette. iPad n'a pas iPhone/iPod ; les tablettes Android n'ont
// pas "Mobile" dans l'UA ; repli = écran tactile petit côté <= 480px.
try {
  const _ua = navigator.userAgent;
  const isPhone = /iPhone|iPod/.test(_ua)
    || (/Android/.test(_ua) && /Mobile/.test(_ua))
    || /Windows Phone|BlackBerry|Opera Mini|IEMobile/.test(_ua)
    || (((('ontouchstart' in window)) || navigator.maxTouchPoints > 0)
        && Math.min(window.screen ? window.screen.width : 9999, window.screen ? window.screen.height : 9999) <= 480);
  if (isPhone) {
    
    setTimeout(() => {
      fetch(base_url + "initialize_playback")
      .then(response => {
        if (!response.ok) throw new Error('initialize_playback failed: ' + response.status);
        return response.text();
      })
      .then(text => console.log('initialize_playback:', text))
      .catch(err => console.error('initialize_playback error:', err));
    },5000);

    };
} catch (err) {
  console.error(err);
}

}, 2000);
}
