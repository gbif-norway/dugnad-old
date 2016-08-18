#!/usr/bin/python
# coding: utf-8

# todo:
# - frie termer
# - geogeo for å sette lat/long (bruk /kart)

import os
import sys
import web
import time
import json
import uuid
import yaml
import hashlib
import logging
import urllib
import urllib2
import gettext
import datetime

import cStringIO as StringIO

from collections import OrderedDict
from web import form, template
from tokyo import cabinet

RESOLVER = "http://data.gbif.no/resolver/"

config = yaml.load(file('config.yaml'))

deepzoom = True
try:
    from gi.repository import Vips
except ImportError:
    deepzoom = False

db = web.database(dbn='sqlite', db='dugnad.db')

def buildform(key):
    if not key in config['forms']: raise Exception("Form not found")
    inputs = []
    recipe = config['forms'][key]
    for i in recipe:
        if not 'name' in i: raise Exception("Needs a name")
        if not 'type' in i: raise Exception("Needs a type")
        k = i['name']
        if i['type'] == "text":
            inputs.append(form.Textbox(k, description = _(k)))
        elif i['type'] == "checkbox":
            inputs.append(form.Checkbox(k, value = "y", description = _(k)))
        elif i['type'] == 'select':
            if 'options' in i:
                options = [''] + i['options']
                inputs.append(form.Dropdown(k, options, description = _(k)))
            elif 'source' in i:
                key = i['source'] + "-" + i['name']
                source = json.loads(web.ctx.metadata.get(key))
                options = [''] + [d['label'] for d in sorted(source)]
                inputs.append(form.Dropdown(k, options, description = _(k)))
	elif i['type'] == 'textfield':
	    inputs.append(form.Textarea(k, description = _(k)))
	elif i['type'] == 'date':
	    inputs.append(form.Textbox("year", description = _('year')))
	    inputs.append(form.Textbox("month", description = _('month')))
	    inputs.append(form.Textbox("day", description = _('day')))
        else: raise Exception("Unknown type %s" % i['type'])
    return form.Form(*inputs)

class index:
    def GET(self):
        return render.index()

class collection:
    def GET(self, key):
        return render.collection(key)

class transcribe:
    def GET(self):
        return render.transcribe(key, record, forms, zoom)

class showannotation:
    def GET(self, key):
        q = { 'id': id }
        anno = db.select('annotations', q, where='id = $id')
        return json.dumps(anno[0])

class showannotations:
    def GET(self, key):
        q = { 'key': key }
        annos = db.select('annotations', q, where ="key = $key")
        final = []
        for anno in annos:
            final.append(json.loads(anno.get('annotation')))
        return json.dumps(final)

class annotate:
    def GET(self, key):
        url = "%s%s.json" % (RESOLVER, key)
        record = json.loads(urllib2.urlopen(url).read())
        date = record.get('dwc:eventDate')

        zoom = False
        if record.get("dwc:associatedMedia"):
            source = urllib.unquote(record.get('dwc:associatedMedia').strip())
            imagekey = hashlib.sha256(source).hexdigest()
            if deepzoom and source.find("http://www.unimus.no/") == 0:
                name = "static/tmp/" + imagekey
                if not os.path.exists(name + "_files"):
                    urllib.urlretrieve(source, "%s.jpg" % name)
                    image = Vips.Image.new_from_file("%s.jpg" % name)
                    image.dzsave(name, layout="dz")
                zoom = True

        if date:
            record['year'], record['month'], record['day'] = date.split("-")
	forms = OrderedDict((form, buildform(form)) for form in config['annotate']['order'])
        for _, form in forms.iteritems(): form.validates(record)
        return render.transcribe(key, record, forms, zoom)

    def POST(self, key):
        uid = session.get('id')
        url = "%s%s.json" % (RESOLVER, key)
        record = json.loads(urllib2.urlopen(url).read())
        today = str(datetime.date.today())
        id = str(uuid.uuid4())
        db.insert('annotations',
            id=id, key=key, user=uid, date=today,
            annotation=json.dumps(web.input()),
            original=json.dumps(record)
        )
        #web.sendmail('noreply@nhmbif.uio.no',
        #    'gbif-drift@nhm.uio.no', '[dugnad] ny annotering',
        #    "http://nhmbif.uio.no/dugnad/annotations/%s" % key)
        raise web.seeother('/dugnad/annotation/%s' % id)

urls = (
    '/dugnad', 'index',
    '/dugnad/', 'index',
    '/dugnad/collection/(.+)', 'collection',
    '/dugnad/transcribe/(.+)', 'transcribe',
    '/dugnad/annotation/(.+)', 'showannotation',
    '/dugnad/annotations/(.+)', 'showannotations',
    '/dugnad/(.+)', 'annotate',
)

languages = ['en_US']
gettext.install('messages', 'lang', unicode=True)
for lang in languages:
    gettext.translation('messages', 'lang', languages = [lang]).install(True)

render = template.render('templates', base='layout', globals= { '_': _ })

app = web.application(urls, locals())
session = web.session.Session(app, web.session.DiskStore('sessions'))

if __name__ == "__main__":
    app.run()

