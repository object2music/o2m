//  o2m.js and o2m.css should be inserted in the mopidy-iris extension
//  in /usr/local/lib/python3.7/dist-packages/mopidy_iris/static
//  and inserted in index.html 
//     <link rel="stylesheet" href="o2m.css">
//    <script type="text/javascript" src="o2m.js"></script>

    window.onload = function() {
      setTimeout(() => {
      list = document.getElementsByClassName('sidebar__menu')[0];
      base_url = window.location.origin.split( '//' )[0]+'//'+window.location.origin.split( '//' )[1].split(':')[0];
      //host = window.location.host;
      base_url += ':6681/api/'
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
      setInterval(update_style_button_box(uid,b), 50000);
      }

    //setInterval(update_style_button_box, 50000);

      //////////////////////////////////////////////////////////////////////////////////
      var b = document.createElement("div");
      b.innerHTML = "<br/>";      
      list.insertBefore(b, list.children[0]);

      var b3 = document.createElement("button");
      b3.innerHTML = "<i class=\"icon icon--material \">explore</i>Reset o2m";
      b3.className = "sidebar__menu__item icon icon--material";
      b3.onclick = function(){  
      var xhr = new XMLHttpRequest();
      xhr.open("GET",base_url+"reset");
      xhr.send();
      setTimeout(() => {
          var but = document.getElementsByTagName('button');
          for(i = 0; i < but.length; i++) {but[i].classList.remove("sidebar__menu__item--active");}
        },500);
      };

      var b4 = document.createElement("button");
      b4.innerHTML = "<i class=\"icon icon--material \">explore</i>Relaunch mopidy";
      b4.className = "sidebar__menu__item icon icon--material";
      b4.onclick = function(){  
      var xhr = new XMLHttpRequest();
      xhr.open("GET",base_url+"relaunch");
      xhr.send();
      setTimeout(() => {
          var but = document.getElementsByTagName('button');
          for(i = 0; i < but.length; i++) {but[i].classList.remove("sidebar__menu__item--active");}
        },500);
      };

      list.insertBefore(b3, list.children[0]);
      list.insertBefore(b4, list.children[0]);

      create_button_box("04DC44D2204B80","Vava");
      create_button_box("049745D2204B80","Maud");
      create_button_box("048F45D2204B80","Liv");
      create_button_box("048745D2204B80","Paul");
      create_button_box("0454F7C90B0280","Pat");
      create_button_box("04CD41193E2580","Podcast");
      create_button_box("04B444D2204B80","Infos");
      create_button_box("last_info","Last infos");
      create_button_box("pod_sismique","Pod Sismique");
      create_button_box("incoming","Incoming");
      create_button_box("04D444D2204B80","New");
      create_button_box("049F45D2204B80","Favorites");
      create_button_box("04CE6F193E2580","Jazz");
      create_button_box("04C52351962280","Danse");
      create_button_box("04463DD2204B80","Calm");
      create_button_box("04AD43D2204B80","Auto");
      create_button_box("auto_simple","Auto simple");

    //Range
      var b5 = document.createElement("input");
      b5.setAttribute("type", "range");
      b5.setAttribute("value", "5");
      b5.setAttribute("min", "0");  
      b5.setAttribute("value", "10");

      list.insertBefore(b5, list.children[0]);
      //<input type="range" value="70" min="0" max="100" oninput="rangevalue.value=value"/>
      //<output id="rangevalue">70</output>




      }, 2000);
    }
