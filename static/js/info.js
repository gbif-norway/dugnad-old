document.addEventListener("DOMContentLoaded", function(e) {
  var subs = document.getElementsByClassName('subproject-thumbnail');
  for(var i = 0; i < subs.length; i++) {
    var remain = 100 - subs[i].getAttribute('data-progress');
    if(remain == 0) {
      subs[i].style.backgroundColor = "rgba(0, 150, 0, 0.4)";
      subs[i].parentNode.href = "";
      subs[i].parentNode.onclick = function(e) { return false; }
      subs[i].parentNode.className = "disabled";
      continue;
    }
    var color = "rgba(200, 0, 0, 0.5)";
    if(remain <= 70) color = "rgba(200, 200, 0, 0.5)";
    if(remain <= 30) color = "rgba(0, 200, 0, 0.5)";
    var g = "linear-gradient(to bottom, white " + remain + "%, " + color + ")";
    subs[i].style.backgroundImage = g;
  }
});

