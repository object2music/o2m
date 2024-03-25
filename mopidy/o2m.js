//  o2m.js and o2m.css should be inserted in the mopidy-iris extension
//  in /usr/local/lib/pythonx.x/dist-packages/mopidy_iris/static
//  and inserted in index.html 
//     <link rel="stylesheet" href="o2m.css">
//    <script type="text/javascript" src="o2m.js"></script>

window.onload = function() {
  setTimeout(() => {
  //------------------INIT--------------------- 
  
  list = document.getElementsByClassName('sidebar__menu')[0];
  base_url = window.location.origin.split( '//' )[0]+'//'+window.location.origin.split( '//' )[1].split(':')[0];
  //host = window.location.host;
  base_url += ':6681/api/'
  backoffice_uri = 'http://51.15.205.150:5001'
  //backoffice_uri += 'sql.php?table=box&sql_query=SELECT+%2A+FROM+%60box%60++%0AORDER+BY+%60box%60.%60favorite%60++DESC&session_max_rows=100&is_browse_distinct=0'
  //alert(base_url)
  
  //Listeners for DOM change in IRIS (o2m_status)
    //Select the node that will be observed for mutations
    const targetNode = document.querySelectorAll("section.list-wrapper")[0];

    // Options for the observer (which mutations to observe)
    const config = {childList: true};
    const flag_o2m_status = 0;

    // Callback function to execute when mutations are observed
    const callback = (mutationList, observer) => {
      for (const mutation of mutationList) {
        setTimeout(() => {
          if (flag_o2m_status == 0)
            {
              flag_o2m_status = 1;
              o2m_status = document.getElementsByClassName("o2m_status");
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

      /*try { 
            if (mutation.target.getElementsByClassName("o2m_status")[0] !== undefined){ 
              uri = mutation.target.getElementsByClassName("o2m_status")[0].innerHTML;
              update = mutation.target.getElementsByClassName("o2m_status")[0];
            }
          } 
          catch (error) {
            console.error(error);
          }
          if (uri) {
            update_o2m_status(update,uri);
          }
      */
        }
    };

    // Create an observer instance linked to the callback function
    const observer = new MutationObserver(callback);

    // Start observing the target node for configured mutations
    observer.observe(targetNode, config);

    // Later, you can stop observing
    //observer.disconnect();


  //----------------FUNCTIONS-------------

    function update_o2m_status(update,uri){
      var xhr10 = new XMLHttpRequest();
        xhr10.onreadystatechange = function() {
        if (xhr10.readyState == xhr10.DONE) {
            if (xhr10.status === 200) {
            update_text = xhr10.responseText;
            try {
              switch (update_text) {
                case 'normal':
                  update_text="library";
                  update.style.backgroundColor = "DarkCyan";
                  break;
                case 'favorites':
                  update.style.backgroundColor = "YellowGreen";
                  break;
                case 'incoming':
                  update.style.backgroundColor = "GoldenRod";
                  break;
                case 'new':
                  update.style.backgroundColor = "orange";
                break;
                case 'trash':
                  update.style.backgroundColor = "FireBrick";
                break;
                case 'hidden':
                  update.style.backgroundColor = "IndianRed";
                break;
                default:
                  update_text="new";
                break;
              }
              update.innerHTML = update_text;
              if ( update.classList.contains('hide') ) {
                update.classList.remove('hide');
                update.classList.add('show');
              }
            } 
            catch (error) {
              console.error(error);
            }
          }}};
        if (uri)
        {
          xhr10.open("GET",base_url+"track_status?uri="+uri);
          xhr10.send();
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
  o2m_status = document.getElementsByClassName("o2m_status");
  for (update of o2m_status) {
      try { 
        uri1 = update.innerHTML;
        update_o2m_status(update,uri1);
      } 
      catch (error) {
        console.error(error);
      }
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