#!/usr/bin/python
# coding: utf-8

# todo:
# - frie termer

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

RESOLVER = "https://data.gbif.no/resolver/"

config = yaml.load(file('config.yaml'))

deepzoom = True
try:
    from gi.repository import Vips
except ImportError:
    deepzoom = False

db = web.database(dbn='sqlite', db='dugnad.db')

class helpers:
  def showfilter(self, config):
    form = buildform('filter', config)
    form.validates(web.input())
    return form

def buildform(key, config):
    if not key in config['forms']: raise Exception("Form not found")
    inputs = []
    recipe = config['forms'][key]
    for i in recipe:
        if not 'name' in i: raise Exception("Needs a name")
        if not 'type' in i: raise Exception("Needs a type")
        k = i['name']
        if i['type'] == "text":
            inputs.append(form.Textbox(k, description = _(k)))
        elif i['type'] == "hidden":
            inputs.append(form.Hidden(k, description = _(k)))
        elif i['type'] == "checkbox":
            inputs.append(form.Checkbox(k, value = "y", description = _(k)))
        elif i['type'] == 'select':
            default = i.get('default', '')
            if 'options' in i:
                options = [''] + i['options']
                inputs.append(form.Dropdown(k, options, description = _(k)))
            elif 'sql' in i:
              db = web.database(dbn='sqlite', db=config['source']['database'])
              results = [v.values()[0] for v in db.query(i['sql'])]
              results = filter(None, results)
              results = [(v, _(v)) for v in results]
              results.insert(0, default)
              inputs.append(form.Dropdown(k, results, description = _(k)))
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

def zoomify(raw):
    try:
        source = urllib.unquote(raw.strip())
        imagekey = hashlib.sha256(source).hexdigest()
        if deepzoom and source.find("http://www.unimus.no/") == 0:
          name = "static/tmp/" + imagekey
          if not os.path.exists(name + "_files"):
            urllib.urlretrieve(source, "%s.jpg" % name)
            image = Vips.Image.new_from_file("%s.jpg" % name)
            image.dzsave(name, layout="dz")
          return "%s.dzi" % imagekey
    except Exception as e:
        raise e

def updatetranscription(id, data):
    finished = True
    now = str(datetime.date.today())
    if data.pop('later', False):
        finished = False
    where = dict(id=id)
    db.update('transcriptions', where=web.db.sqlwhere(where),
        date=now, finished=finished,
        annotation=json.dumps(data)
    )
    
def savetranscription(uid, pkey, data):
    project = yaml.load(open('projects/' + pkey + '.yaml'))
    finished = True
    if data.pop('skip', False):
        raise Exception("Skipped")
    if data.pop('later', False):
        finished = False
    now = str(datetime.date.today())
    key = data[project['key']]
    id = str(uuid.uuid4())
    db.insert('transcriptions',
        id=id, project=pkey, key=key, user=uid, date=now, finished=finished,
        annotation=json.dumps(data)
    )

class index:
    def GET(self):
        return render.index()

class unfinished:
    def GET(self, id):
        uid = session.get('id')
        data = web.input()
        try:
            where = dict(id = id)
            recs = db.select('transcriptions', where = web.db.sqlwhere(where))
            record = recs[0]
            project = yaml.load(open('projects/' + record['project'] + '.yaml'))
            anno = json.loads(record['annotation'])
            pdb = web.database(dbn='sqlite', db=project['source']['database'])
            origid = dict(occurrenceID = record['key'])
            origs = pdb.select(project['source']['table'],
                where = web.db.sqlwhere(origid), limit=1)
            orig = origs[0]
            zoom = False
            if orig.get("associatedMedia"):
                zoom = zoomify(orig['associatedMedia'])
            forms = OrderedDict((form, buildform(form, project)) for form in project['annotate']['order'])
            for _, form in forms.iteritems(): form.validates(anno)
            return render.transcribe("unfinished/" + record['id'], anno, forms, zoom, uid, project, False)
        except ValueError as e:
            raise web.seeother('/dugnad/unfinished')

    def POST(self, id):
        uid = session.get('id')
        updatetranscription(id, web.input())
        raise web.seeother("/dugnad/unfinished")


class listunfinished:
    def GET(self):
        uid = session.get('id')
        recs = db.select('transcriptions')
        return render.list(recs)

class project:
    def GET(self, key):
      uid = session.get('id')
      try:
        project = yaml.load(open('projects/' + key + '.yaml'))
        url = "%s%s.json" % (RESOLVER, key)
        pdb = web.database(dbn='sqlite', db=project['source']['database'])
        filters = {}
        data = web.input()
        if project['forms'].get('filter'):
          for f in project['forms']['filter']:
            if data.get(f['name']) and data[f['name']] != "None":
              filters[f['name']] = data[f['name']]
        if len(filters) < 1: filters = None
        recs = pdb.select(project['source']['table'], where=filters,
            limit=1, order="RANDOM()")
        zoom = False
        try:
          record = recs[0]
          if record.get('genus'):
            record['scientificName'] = "%s %s" % (
                record.get('genus'), record.get('species')
            )
          if record.get("associatedMedia"):
            zoom = zoomify(record['associatedMedia'])
        except IndexError as e:
          record = None
        forms = OrderedDict((form, buildform(form, project)) for form in project['annotate']['order'])
        for _, form in forms.iteritems(): form.validates(record)
        return render.transcribe("project/" + key, record, forms, zoom, uid, project, True)
      except ValueError as e:
        raise web.seeother('/dugnad/')

    def POST(self, pkey):
        uid = session.get('id')
        savetranscription(uid, pkey, web.input())
        referer = web.ctx.env.get('HTTP_REFERER', '/dugnad/')
        raise web.seeother(referer)

class showannotation:
    def GET(self, key):
        key, ext = os.path.splitext(key)
        q = { 'id': key }
        annos = db.select('annotations', q, where='id = $id')
        if ext:
          if ext == ".json":
            return annos[0]['annotation']
          else:
            return web.notfound()
        return render.show(annos[0])

class showannotations:
    def GET(self, key):
        key, ext = os.path.splitext(key)
        q = { 'key': key }
        final = []
        annos = db.select('annotations', q, where ="key = $key")
        for anno in annos:
            final.append(json.loads(anno.get('annotation')))
        if ext:
          if ext == ".json":
            return json.dumps(final)
          else:
            return web.notfound()
        return render.annotations(final)

class annotate:
    def GET(self, key):
        uid = session.get('id')
        key = key.replace("urn:catalog:", "")
        url = "%s%s.json" % (RESOLVER, key)
        try:
          raw = json.loads(urllib2.urlopen(url).read())
          record = {}
          for k,v in record.iteritems():
            record[k.replace("dwc:", "")] = v
          date = record.get('eventDate')
          zoom = zoomify(record['associatedMedia'])
          if date:
            record['year'], record['month'], record['day'] = date.split("-")
          forms = OrderedDict((form, buildform(form, config)) for form in config['annotate']['order'])
          for _, form in forms.iteritems(): form.validates(record)
          return render.transcribe(key, record, forms, zoom, uid, config, True)
        except Exception as e:
          message = "%s not found (%s)" % (key, e)
          return render.error(message)

    def POST(self, key):
        uid = session.get('id')
        key = key.replace("urn:catalog:", "")
        url = "%s%s.json" % (RESOLVER, key)
        record = json.loads(urllib2.urlopen(url).read())
        now = str(datetime.date.today())
        finished = True
        id = str(uuid.uuid4())
        if 'later' in data: finished = False
        db.insert('annotations',
            id=id, key=key, user=uid, date=now, finished=finished,
            annotation=json.dumps(web.input()),
            original=json.dumps(record)
        )
        web.sendmail('noreply@nhmbif.uio.no',
            'gbif-drift@nhm.uio.no', '[dugnad] ny annotering',
            "https://nhmbif.uio.no/dugnad/annotation/%s / https://nhmbif.uio.no/dugnad/annotations/%s" % (id, key))
        raise web.seeother('/dugnad/annotation/%s' % id)

urls = (
    '/dugnad', 'index',
    '/dugnad/', 'index',
    '/dugnad/unfinished', 'listunfinished',
    '/dugnad/unfinished/(.+)', 'unfinished',
    '/dugnad/project/(.+)', 'project',
    '/dugnad/annotation/(.+)', 'showannotation',
    '/dugnad/annotations/(.+)', 'showannotations',
    '/dugnad/(.+)', 'annotate',
)

languages = ['en_US']
gettext.install('messages', 'lang', unicode=True)
for lang in languages:
    gettext.translation('messages', 'lang', languages = [lang]).install(True)

render = template.render('templates', base='layout', globals= {
    '_': _,
    'json': json,
    'helper': helpers(),
    'web': web,
    'config': config
})

app = web.application(urls, locals())
session = web.session.Session(app, web.session.DiskStore('sessions'))
web.config.session_parameters['timeout'] = 2592000 # 30 * 24 * 60 * 60
web.config.session_parameters['cookie_domain'] = "127.0.0.1"
web.config.session_parameters['cookie_path'] = "/"
web.config.debug = True

if __name__ == "__main__":
    app.run()

