
    window.onload = function() {
      setTimeout(() => {
      list = document.getElementsByClassName('sidebar__menu')[0];
      base_url = 'http://pi.local:6681'


      var b = document.createElement("div");
      b.innerHTML = "<br/>";      
      list.insertBefore(b, list.children[0]);

      var b3 = document.createElement("button");
      b3.innerHTML = "<i class=\"icon icon--material \">explore</i>Reset";
      b3.className = "sidebar__menu__item icon icon--material";
      b3.style = "cursor: pointer; background-color: transparent;"
        b3.onclick = function(){  
        var xhr = new XMLHttpRequest();
            xhr.open("GET",base_url+"/api/reset");
            xhr.send();
         };
      list.insertBefore(b3, list.children[0]);


      var b = document.createElement("button");
      b.innerHTML = "<i class=\"icon icon--material \">recent_actors</i>Podcast";
      b.className = "sidebar__menu__item icon icon--material";
      b.style = "cursor: pointer; background-color: transparent;"
        b.onclick = function(){  
        var xhr = new XMLHttpRequest();
            xhr.open("GET",base_url+"/api/tag?option_type=podcast");
            xhr.send();
         };
      list.insertBefore(b, list.children[0]);

      var b = document.createElement("button");
      b.innerHTML = "<i class=\"icon icon--material \">recent_actors</i>Incoming";
      b.className = "sidebar__menu__item icon icon--material";
      b.style = "cursor: pointer; background-color: transparent;"
        b.onclick = function(){  
        var xhr = new XMLHttpRequest();
            xhr.open("GET",base_url+"/api/tag?option_type=incoming");
            xhr.send();
         };
      list.insertBefore(b, list.children[0]);

      var b = document.createElement("button");
      b.innerHTML = "<i class=\"icon icon--material \">recent_actors</i>New";
      b.className = "sidebar__menu__item icon icon--material";
      b.style = "cursor: pointer; background-color: transparent;"
        b.onclick = function(){  
        var xhr = new XMLHttpRequest();
            xhr.open("GET",base_url+"/api/tag?option_type=new");
            xhr.send();
         };
      list.insertBefore(b, list.children[0]);

      var b = document.createElement("button");
      b.innerHTML = "<i class=\"icon icon--material \">recent_actors</i>Favorites";
      b.className = "sidebar__menu__item icon icon--material";
      b.style = "cursor: pointer; background-color: transparent;"
        b.onclick = function(){  
        var xhr = new XMLHttpRequest();
            xhr.open("GET",base_url+"/api/tag?option_type=favorites");
            xhr.send();
         };
      list.insertBefore(b, list.children[0]);

      var b2 = document.createElement("button");
      b2.innerHTML = "<i class=\"icon icon--material \">queue_music</i>Auto simple";
      b2.className = "sidebar__menu__item icon icon--material";
      b2.style = "cursor: pointer; background-color: transparent;"
        b2.onclick = function(){  
        var xhr = new XMLHttpRequest();
            xhr.open("GET",base_url+"/api/auto_simple");
            xhr.send();
         };
      list.insertBefore(b2, list.children[0]);

      var b1 = document.createElement("button");
      b1.innerHTML = "<i class=\"icon icon--material \">queue_music</i>Auto";
      b1.className = "sidebar__menu__item icon icon--material";
      b1.style = "cursor: pointer; background-color: transparent;"
        b1.onclick = function(){  
        var xhr = new XMLHttpRequest();
            xhr.open("GET",base_url+"/api/auto");
            xhr.send();
         };
      list.insertBefore(b1, list.children[0]);


      }, 2000);
    }
