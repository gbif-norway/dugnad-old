var T = {};

T.http = function(method, uri, query, callback) {
  var req = new XMLHttpRequest();
  req.onreadystatechange = function() {
    if(req.readyState == 4 && req.status == 200) {
      callback(req.responseText, req.status);
    }
  }
  req.open(method, uri, true);
  req.send(query);
}

T.getmarkings = function(page) {
  var base = document.location + "";
  var url = base.replace(/\/$/, "").replace("#", "") + "/markings/" + page;
  T.http("GET", url, null, function(raw) {
    var data = JSON.parse(raw);
    for(var i = 0; i < data.length; i++) {
      var cv = overlay.fabricCanvas();
      cv.loadFromJSON(data[i], cv.renderAll.bind(cv), function(o, obj) {
        obj.stroke = "rgba(255, 255, 0, 0.3)";
        obj.selectable = false;
      });
    }
  });
}

T.georeference = function(layer) {
  document.getElementById('decimalLatitude').value = "";
  document.getElementById('decimalLongitude').value = "";
  document.getElementById('coordinateUncertaintyInMeters').value = "";
  document.getElementById('footprintWKT').value = "";

  if (layer instanceof L.Circle) {
    var latlng = layer.getLatLng();
    document.getElementById('decimalLatitude').value = latlng.lat.toFixed(7);
    document.getElementById('decimalLongitude').value = latlng.lng.toFixed(7);
    document.getElementById('coordinateUncertaintyInMeters').value =
      parseInt(layer.getRadius());
  } else {
    var wkt = new Wkt.Wkt();
    wkt.read(JSON.stringify(layer.toGeoJSON()));
    document.getElementById('footprintWKT').value = wkt.write();
  }
}

T.checkcoordinates = function(e) {
  return;
  var latitude = document.getElementsByName('decimalLatitude')[0];
  var longitude = document.getElementsByName('decimalLongitude')[0];
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
  if(el.name == 'decimalLatitude' || el.name == 'decimalLongitude') return;
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

  var url = "https://opencache.statkart.no/gatekeeper/gk/gk.open";
  var opts = {
    layers: 'topo2',
    format: 'image/png',
    transparent: true,
    attribution: "Kartverket"
  };
  var statkart = new L.TileLayer.WMS(url, opts);

  if(document.getElementById('map')) {
    T.map = L.map('map').setView([59, 9], 8);

    T.map.addLayer(statkart);
    var georef = new L.FeatureGroup();
    T.map.addLayer(georef);
  
    var control = new L.Control.Draw({
      edit: { featureGroup: georef },
      draw: {
        marker: false,
        polyline: false
      }
    });

    var measure = new L.Control.LinearMeasurement({
      unitSystem: 'metric',
      color: '#000000'
    });
    T.map.addControl(measure);

    T.map.addControl(control);
    L.control.scale({
      position: 'topleft',
      imperial: false,
      maxWidth: 200
    }).addTo(T.map);

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
  }

  T.toggle('toggle-help', 'help');

  var footprint = document.getElementsByName('verbatimWKT')[0];
  if(footprint && footprint.value) {
    var wkt = new Wkt.Wkt();
    wkt.read(footprint.value);
    var obj = wkt.toObject(T.map.defaults);
    obj.addTo(T.map);
    T.map.fitBounds(obj.getBounds(), {
      paddingBottomRight: [300, 150],
      paddingTopLeft: [0, 100]
    });
  } else {
    var latitude = document.getElementsByName('verbatimLatitude')[0];
    var longitude = document.getElementsByName('verbatimLongitude')[0];
    var uncertainty = document.getElementById('verbatimUncertaintyInMeters');
    if(latitude && longitude && latitude.value && longitude.value) {
      var lat = parseFloat(latitude.value);
      var lon = parseFloat(longitude.value);
      var radius = (uncertainty && uncertainty.value) ? uncertainty.value : 10;
      T.marker = L.circle([lat, lon], radius, {
        weight: 2,
        color: "black",
        interactive: false
      });
      T.map.addLayer(T.marker);
      T.marker.addTo(T.map);
      latitude.onkeyup = T.checkcoordinates;
      longitude.onkeyup = T.checkcoordinates;
      T.map.panTo(T.marker.getLatLng());
      T.map.fitBounds(T.marker.getBounds(), {
        paddingBottomRight: [300, 150],
        paddingTopLeft: [0, 100]
      });
    }
  }
  var footprint = document.getElementsByName('footprintWKT')[0];
  if(footprint && footprint.value) {
    var wkt = new Wkt.Wkt();
    wkt.read(footprint.value);
    var obj = wkt.toObject(T.map.defaults);
    obj.addTo(T.map);
    T.map.fitBounds(obj.getBounds(), {
      paddingBottomRight: [300, 150],
      paddingTopLeft: [0, 100]
    });
  }

  var chatln = document.getElementById('open-chat');
  if(chatln) {
    chatln.onclick = function(e) {
      var chat = document.getElementById('chat-overlay');
      if(chat) chat.style.display = "block";
      return false;
    }
  }

  var showMap = document.getElementById('show-map');
  if(showMap) {
    var replacement = showMap.getAttribute('data-replace');
    var current = showMap.textContent;
    showMap.onclick = function(e) {
      var overlay = document.getElementById('map-overlay');
      if(!overlay) return;
      if(overlay.style.visibility === "visible") {
        e.target.textContent = current;
        overlay.style.visibility = "hidden";
      } else {
        e.target.textContent = replacement;
        overlay.style.visibility = "visible";
      }
    }
    if(!showMap.getAttribute('data-document'))
      showMap.click();
  }

  var helpln = document.getElementsByClassName('help');
  for(var i = 0; i < helpln.length; i++) {
    helpln[i].setAttribute('data-title', helpln[i].getAttribute('title'));
    helpln[i].removeAttribute('title');
    helpln[i].onclick = function(e) {
      var help = document.getElementById('helptext');
      var text = e.target.parentNode.getAttribute('data-title');
      help.innerHTML = text.replace("\n\n", "<p>").replace("\n", "<br>");
      return false;
    }
  }

  var inputs = document.getElementsByTagName('input');
  for(var i = 0; i < inputs.length; i++) {
    if(inputs[i].getAttribute('data-pick')) {
      (function(input) {
        var choices = JSON.parse(input.getAttribute('data-pick'));
        new autoComplete({
          delay: 0,
          selector: input,
          minChars: 1,
          cache: true,
          source: function(term, suggest) {
            term = term.toLowerCase();
            var hits = [];
            for(i = 0; i < choices.length; i++)
              if(~choices[i].toLowerCase().indexOf(term)) hits.push(choices[i]);
            suggest(hits);
          },
          onSelect: function(e, term, item) {
            e.preventDefault();
          }
        });
      })(inputs[i]);
    }
    if(inputs[i].getAttribute('data-url')) {
      (function(input) {
        var url = input.getAttribute('data-url');
        new autoComplete({
          delay: 150,
          selector: input,
          minChars: 3,
          cache: true,
          source: function(term, suggest) {
            term = term.toLowerCase();
            T.http("GET", url + "?q=" + term, null, function(raw) {
              var data = JSON.parse(raw);
              suggest(data);
            });
          },
          renderItem: function(item, search) {
            search = search.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
            var re = new RegExp("(" + search.split(' ').join('|') + ")", "gi");
            var data = JSON.stringify(item)
            var div = document.createElement('div');
            div.className = 'autocomplete-suggestion';
            div.setAttribute('data-val', item.name);
            div.setAttribute('data-all', data);
            div.innerHTML = item.name.replace(re, "<b>$1</b>");
            return div.outerHTML;
          },
          onSelect: function(e, term, item) {
            var raw = item.getAttribute('data-all');
            var data = JSON.parse(raw);
            for(k in data) {
              if(k == "geography") {
                var wkt = new Wkt.Wkt();
                wkt.read(data[k]);
                var footprint = document.getElementById("footprintWKT");
                var obj = wkt.toObject(T.map.defaults);
                obj.addTo(T.map);
                T.map.fitBounds(obj.getBounds(), {
                  paddingBottomRight: [300, 150],
                  paddingTopLeft: [0, 100]
                });
                if(footprint) {
                  footprint.value = wkt.write();
                }
              } else if(k == "id") {
                var locationid = document.getElementById("locationID");
                if(locationid) {
                  locationid.value = "NVE:" + data[k];
                }
              } else if(k == "masl") {
                var elevation = document.getElementById("verbatimElevation");
                if(elevation) {
                  elevation.value = data[k];
                }
              }
            }
            e.preventDefault();
          }
        });
      })(inputs[i]);
    }
  }

  var mark = document.getElementById("mark-page");
  if(mark) {
    mark.onclick = function(e) {
      if(viewer && markpage) {
        markpage(e.target);
      }
      return false;
    }
  }
});

