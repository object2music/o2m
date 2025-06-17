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
  
  //Listeners for DOM change in IRIS (o2m_status)
    //Node of lists tracks changing 
    const targetNode = document.querySelectorAll("section.list-wrapper")[0];

    // Options for the observer (which mutations to observe)
    const config = {childList: true};
    flag_o2m_status = 0;

    // Callback function to execute when mutations are observed
    const callback = (mutationList, observer) => {
      for (const mutation of mutationList) {
        setTimeout(() => {
          if (flag_o2m_status == 0)
            {
              flag_o2m_status = 1;
              for (update of o2m_status) {
                try { 
                      uri1 = update.innerHTML;
                      update_o2m_status(update,uri1);
                    } 
                    catch (error) {
                      console.error(error);
                    }
              }
              flag_o2m_status = 0;
            }
        },60000);
        }
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
    
  //----------------FUNCTIONS-------------

    function update_o2m_status(update,uri,show = "min"){
      if (!uri.includes('library - ') && !uri.includes('favorites - ') && !uri.includes('incoming - ') && !uri.includes('podcast - ') && !uri.includes('info - ') && !uri.includes('new') && !uri.includes('trash - ') && !uri.includes('hidden - ') && !uri.includes('normal - ')) {
        var xhr10 = new XMLHttpRequest();
        xhr10.onreadystatechange = function() {
        if (xhr10.readyState == xhr10.DONE) {
            if (xhr10.status === 200) {
            update_text = xhr10.responseText;
            try {
                if ((update_text.includes('podcast')) || (uri.includes('podcast+'))){
                  update.style.backgroundColor = "Gainsboro";
                  //reg = /podcast+.* -/
                  update_text = update_text.replace("normal","podcast");
                }
                else if (update_text.includes('normal')){
                  update_text=update_text.replace("normal", "library");
                  update.style.backgroundColor = "LightSkyBlue";
                }
                else if (update_text.includes('favorites')){
                  update.style.backgroundColor = "YellowGreen";
                }
                else if (update_text.includes('incoming')){
                  update.style.backgroundColor = "GoldenRod";
                  }
                else if (update_text.includes('new')){
                  update.style.backgroundColor = "orange";
                }
                else if (update_text.includes('trash')){
                  update.style.backgroundColor = "FireBrick";
                }
                else if (update_text.includes('hidden')){
                  update.style.backgroundColor = "IndianRed";
                }
                else if (update_text.includes('info')){
                  update.style.backgroundColor = "Gainsboro";
                }
                

              if (show == "min")
              {
                //update_text = update_text.split(' - ')[0];
              }
              update.innerHTML = update_text;

            if ( !update.classList.contains('show') ) {
                update.classList.add('show');
            } 
            if ( update.classList.contains('hide') ) {
              update.classList.remove('hide');
            } 
          }            
            catch (error) {
              console.error(error);
            }
          }}};
        if (uri)
        {
          xhr10.open("GET",base_url+"track_status?uri="+encodeURIComponent(uri));
          xhr10.send();
        }
    }
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
          list.insertBefore(b8, list.children[0]);
        }}};
  xhr1.open("GET",base_url+"spotipy_check");
  xhr1.send();

//RESET
  var b4 = document.createElement("button");
  b4.innerHTML = "<i class=\"icon icon--material \">explore</i>Relaunch mopidy";
  b4.className = "sidebar__menu__item icon icon--material";
  b4.onclick = function(){  
  var xhr = new XMLHttpRequest();
  xhr.open("GET",base_url+"restart_mopidy");
  xhr.send();
  setTimeout(() => {
      var but = document.getElementsByTagName('button');
      for(i = 0; i < but.length; i++) {but[i].classList.remove("sidebar__menu__item--active");}
    },500);
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
  {setTimeout(() => {
    o2m_status_update();
  }, "10000");}

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

}, 2000);
}