document.addEventListener("DOMContentLoaded", function(e) {
  var subs = document.getElementsByClassName('subproject-thumbnail');
  for(var i = 0; i < subs.length; i++) {
    var progress = 100 - subs[i].getAttribute('data-progress');
    var gradient = "linear-gradient(to bottom, white " + progress + "%, rgba(0, 150, 0, 0.7))";
    subs[i].style.backgroundImage = gradient;
  }
});
