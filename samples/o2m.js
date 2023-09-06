//  o2m.js and o2m.css should be inserted in the mopidy-iris extension
//  in /usr/local/lib/pythonx.x/dist-packages/mopidy_iris/static
//  and inserted in index.html 
//     <link rel="stylesheet" href="o2m.css">
//    <script type="text/javascript" src="o2m.js"></script>

    window.onload = function() {
      setTimeout(() => {
      list = document.getElementsByClassName('sidebar__menu')[0];
      base_url = window.location.origin.split( '//' )[0]+'//'+window.location.origin.split( '//' )[1].split(':')[0];
      //host = window.location.host;
      base_url += ':6691/api/'
      //alert(base_url)

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
      /*
      var b3 = document.createElement("button");
      b3.innerHTML = "<i class=\"icon icon--material \">explore</i>Reset o2m";
      b3.className = "sidebar__menu__item icon icon--material";
      b3.onclick = function(){  
      var xhr = new XMLHttpRequest();
      xhr.open("GET",base_url+"reset_o2m");
      xhr.send();
      setTimeout(() => {
          var but = document.getElementsByTagName('button');
          for(i = 0; i < but.length; i++) {but[i].classLmainist.remove("sidebar__menu__item--active");}
        },500);
      };
      */


      //BOXES Edit
      //http://localhost:5011/index.php?route=/sql&pos=0&db=o2m&table=box
      var a1 = document.createElement("a");
      a1.innerHTML = "Backoffice";
      a1.setAttribute("href","http://localhost:5011/index.php?route=/sql&pos=0&db=o2m&table=box");
      a1.setAttribute("target","_blank");
      list.insertBefore(a1, list.children[0]);

      var a1 = document.createElement("br");
      list.insertBefore(a1, list.children[0]);

    //SPOTIPY
    var xhr1 = new XMLHttpRequest();

    xhr1.onreadystatechange = function() {
        if (xhr1.readyState == xhr1.DONE) {
            if (xhr1.status === 200) {
            sp = xhr1.responseText;

            var a1 = document.createElement("a");
            a1.innerHTML = sp;
            a1.setAttribute("href",base_url+sp);
            a1.setAttribute("target","_blank");
            list.insertBefore(a1, list.children[0]);

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

      //BOXES FROm API
      var xhr5 = new XMLHttpRequest();

      xhr5.onreadystatechange = function() {
          if (xhr5.readyState == xhr5.DONE) {
              if (xhr5.status === 200) {
              boxes = xhr5.responseText;
              const obj = JSON.parse(boxes);
              for(let i = 0; i < obj.length; i++) {
                create_button_box(obj[i].uid,obj[i].description);
              }
            }}};
      xhr5.open("GET",base_url+"box_favorites");
      xhr5.send();


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
      slider.addEventListener("wheel", function(e){
        if (e.deltaY < 0){
          slider.valueAsNumber += 1;
        }else{
          slider.value -= 1;
        }
        e.preventDefault();
        e.stopPropagation();
      })


    }, 2000);
    }