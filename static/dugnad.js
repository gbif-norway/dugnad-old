var T = {};

T.georeference = function(layer) {
  document.getElementById('decimalLatitude').value = "";
  document.getElementById('decimalLongitude').value = "";
  document.getElementById('coordinateUncertaintyInMeters').value = "";
  document.getElementById('footprintWKT').value = "";

  if (layer instanceof L.Circle) {
    var latlng = layer.getLatLng();
    document.getElementById('decimalLatitude').value = latlng.lat;
    document.getElementById('decimalLongitude').value = latlng.lng;
    document.getElementById('coordinateUncertaintyInMeters').value =
      layer.getRadius();
  } else {
    var wkt = new Wkt.Wkt();
    wkt.read(JSON.stringify(layer.toGeoJSON()));
    document.getElementById('footprintWKT').value = wkt.write();
  }
}

T.checkcoordinates = function(e) {
  var latitude = document.getElementsByName('latitude')[0];
  var longitude = document.getElementsByName('longitude')[0];
  latitude.className = ''; longitude.className = '';
  T.map.removeLayer(T.marker);

  var degexp = /^([\d\-.*,°d\s]+)[\s'm]*([nsew])/i
    var rawlat = latitude.value.match(degexp);
  var rawlon = longitude.value.match(degexp);
  if(rawlat && rawlon) {
    var lat = degtodec(rawlat[2], rawlat[1]);
    var lon = degtodec(rawlon[2], rawlon[1]);
    var acc = precision(rawlat[1], rawlon[1]);

    T.marker.setRadius(acc);
    T.marker.setLatLng([lat, lon]);
    T.marker.addTo(T.map);
    switch(acc) {
      case 30:
        T.map.setZoom(13); break;
      case 1847:
        T.map.setZoom(11); break;
      case 110874:
        T.map.setZoom(8); break;
    }
    latitude.className = 'ok'; longitude.className = 'ok';
    T.map.panTo(T.marker.getLatLng());
  }
}

T.toggle = function(id, targetId, on, off) {
  var toggler = document.getElementById(id);
  var target = document.getElementById(targetId);
  if(toggler && target) {
    toggler.onclick = function() {
      if(target.style.display == 'block') {
        target.style.display = 'none';
        document.cookie = targetId + '=0';
        toggler.textContent = 'Show ' + targetId + '…';
        if(off) off();
      } else {
        target.style.display = 'block';
        document.cookie = targetId + '=1';
        toggler.textContent = 'Hide ' + targetId + '…';
        if(on) on();
      }
    }
  }
  if(getcookie(targetId) == '1')
    toggler.click();
}

T.help = function(e) {
  var help = document.getElementById('help');
  var text = e.target.getAttribute('data-help');
  if(help && text)
    help.innerHTML = text;
}

T.next = function(e) {
  if(e.keyCode == 13 || e.which == 13) {
    e.preventDefault();
    return false;
  }
  return true;
}

T.validate = function(e) {
  var el = e.target;
  if(el.name == 'latitude' || el.name == 'longitude') return;
  el.className = '';
  if(!el.value || el.value == '')
    return;

  switch(el.name) {
    case 'elevation':
      if(!el.value.match(/\d/))
        el.className = 'error';
      break;
    case 'month':
      if(el.value.match(/\d/) && (el.value > 12 || el.value < 1))
        el.className = 'error';
      break;
    case 'day':
      var day = parseInt(el.value);
      if(!el.value.match(/\d/) || day < 1 || day > 31)
        el.className = 'error';
      break;
  }
}

function getcookie(name) {
  var id = name + '=';
  var cookies = document.cookie.split(';');
  for(var i=0; i < cookies.length; i++) {
    var cookie = cookies[i].trim();
    if(cookie.indexOf(id) == 0)
      return cookie.substring(id.length, cookie.length);
  }
  return '';
}

function degtodec(nsew, coords) {
  var parts = coords.split(/[-.*°d\s]/);
  var degrees = parseInt(parts[0]), minutes = parts[1], seconds = parts[2];
  if(minutes)
    degrees = degrees + (parseInt(minutes) / 60);
  if(seconds)
    degrees = degrees + (parseInt(seconds) / 3600);
  if(nsew.match(/[ws]/i))
    return -degrees;
  return degrees;
}

function precision(lat, lon) {
  var parts = lat.split(/[-.*°d\s]/);
  var degrees = parseInt(parts[0]), minutes = parts[1], seconds = parts[2];
  if(seconds) return 30;
  if(minutes) return 1847;
  return 110874;
}

document.addEventListener("DOMContentLoaded", function(e) {
  window.ActiveXObject = null;

  var url = "https://cartocdn_{s}.global.ssl.fastly.net/base-eco/{z}/{x}/{y}@2x.png";
  var att = '<a href="https://www.mapzen.com/rights">Attribution.</a>. Data &copy;<a href="https://openstreetmap.org/copyright">OSM</a> contributors.';
  var osm = new L.TileLayer(url, { minZoom: 1, maxZoom: 16, attribution: att });

  T.map = L.map('map').setView([0, 0], 2);
  T.map.addLayer(osm);

  var georef = new L.FeatureGroup();
  T.map.addLayer(georef);

  var control = new L.Control.Draw({
    edit: { featureGroup: georef }
  });
  T.map.addControl(control);
	
	T.map.on('draw:created', function(e) {
    georef.clearLayers();
    T.georeference(e.layer);
    georef.addLayer(e.layer);
	});
	T.map.on('draw:edited', function(e) {
    e.layers.eachLayer(function(layer) {
      georef.clearLayers();
      T.georeference(layer);
      georef.addLayer(layer);
    });
  });

  T.toggle('toggle-help', 'help');
  T.toggle('toggle-map', 'map', function() {
    T.map.invalidateSize(false);
  });

  var form = document.getElementById('transcription');
  if(form) {
    for(var i=0; i < form.length; i++) {
      form.elements[i].addEventListener('keypress', T.next, false);
      form.elements[i].addEventListener('change', T.validate, false);
      form.elements[i].addEventListener('focus', T.help, false);
    }
    var save = document.getElementsByName('save')[0];
    if(save) {
      save.onclick = function(e) {
        var nodate = document.getElementsByName('nodate')[0];
        if(nodate.checked)
          return true;
        var year = document.getElementsByName('year')[0];
        if(year && !year.value || year.value == "")
          return false;
      }
    }
  }

  var latitude = document.getElementsByName('latitude')[0];
  var longitude = document.getElementsByName('longitude')[0];
  if(latitude && longitude) {
    T.marker = L.circle([0, 0], 1000);
    latitude.onkeyup = T.checkcoordinates;
    longitude.onkeyup = T.checkcoordinates;
  }
});

