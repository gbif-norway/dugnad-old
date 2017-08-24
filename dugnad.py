#!/usr/bin/python
# coding: utf-8

import metnopy

import os
import re
import sys
import web
import glob
import time
import json
import uuid
import yaml
import string
import hashlib
import logging
import urllib
import urllib2
import gettext
import datetime

import cStringIO as StringIO

from itertools import islice
from collections import OrderedDict
from web import form, template
from tokyo import cabinet

from yapsy.PluginManager import PluginManager
from yapsy.IPlugin import IPlugin
from dugnadplugins import *

manager = PluginManager()
manager.setCategoriesFilter({
    'Chart': IChartPlugin
})
manager.setPluginPlaces(["plugins"])
manager.collectPlugins()

logging.basicConfig(level=logging.INFO)

RESOLVER = "https://data.gbif.no/resolver/"

config = yaml.load(file('config.yaml'))
prefix = re.search(r"http?s:\/\/[^\/]+(.*)", config['prefix']).groups()[0]

def crumbs():
    if not 'crumbs' in web.ctx: web.ctx['crumbs'] = []
    return web.ctx['crumbs']

deepzoom = True
try:
    from gi.repository import Vips
except ImportError:
    deepzoom = False

db = web.database(dbn='sqlite', db='dugnad.db')

class HelpBox(object):
    def __init__(self, text):
        self.text = text

    def name(self):
        return text

class helpers:
  def name(self):
    return session.get('name')

  def uid(self):
    return session.get('id')

  def admin(self):
    return session.get('admin')

  def showfilter(self, config):
    form = buildform('filter', config)
    form.validates(web.input())
    return form

def getstats(key, project):
    stats = []
    res = db.query("select count(distinct(user)) as count from transcriptions where project = '%s'" % key)
    stats.append(("users-total", res[0]['count']))
    res = db.query("select count(distinct(user)) as count from transcriptions where project = '%s' and date = date()" % key)
    stats.append(("users-today", res[0]['count']))

    res = db.query("select count(*) as count from transcriptions where project = '%s'" % key)
    stats.append(("transcriptions-total", res[0]['count']))
    res = db.query("select count(*) as count from transcriptions where project = '%s' and date = date()" % key)
    stats.append(("transcriptions-today", res[0]['count']))
    return stats

def getusername(label):
    if not label: return _("anonymous")
    try:
      where = dict(uid=label)
      udb = web.database(dbn='sqlite', db="/site/gbif/loans/users.db")
      rec = udb.select("users", where=where)[0]
      return rec.get('nick') or rec.get('name', _('unknown'))
    except Exception:
      return _("unknown")

def helplink(text):
    if not text: return ""
    return "<a class=help title='%s'><img src='%s/images/help.png'></a>" % (_(text), config['base'])

def buildform(key, config):
    if not key in config['forms']: raise Exception("Form not found")
    inputs = []
    recipe = config['forms'][key]
    for i in recipe:
        if not 'name' in i: raise Exception("Needs a name")
        if not 'type' in i: raise Exception("Needs a type")
        k = i['name']
        if i['type'] == "text":
            inputs.append(form.Textbox(k, description = _(k), post = helplink(i.get('help'))))
        elif i['type'] == "hidden":
            inputs.append(form.Hidden(k, description = _(k)))
        elif i['type'] == "checkbox":
            inputs.append(form.Checkbox(k, value = "y", description = _(k), post = helplink(i.get('help'))))
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
          inputs.append(form.Textarea(k, description = _(k), post = helplink(i.get('help'))))
        elif i['type'] == 'date':
          inputs.append(form.Textbox("year", description = _('year'), post = helplink('help-year')))
          inputs.append(form.Textbox("month", description = _('month'), post = helplink('help-month')))
          inputs.append(form.Textbox("day", description = _('day'), post = helplink('help-day')))
        else: raise Exception("Unknown type %s" % i['type'])

    return form.Form(*inputs)

def chart(raw):
    chart = {}
    chart['id'] = raw['name']
    chart['name'] = _(raw['name'])
    chart['description'] = _(raw['description'])
    chart['type'] = raw['type']
    chart['labels'] = []
    chart['series'] = []
    for i, item in enumerate(raw.get('data', [])):
        if item['type'] == 'sql':
            chart['labels'].append(_(item.get('label')))
            db = web.database(dbn='sqlite', db=item['database'])
            key = item.get('key', 'result')
            chart['series'].append(db.query(item['sql'])[0][key])
        if item['type'] == 'count':
            db = web.database(dbn='sqlite', db=item['database'])
            results = db.query(item['sql'])
            chart['series'].append([])
            if 'plugin' in item:
                plugin = manager.getPluginByName(item['plugin'], 'Chart')
                if plugin:
                    chart = plugin.plugin_object.chart(chart, results[0], i)
            else:
                for result in results:
                    if i == 0:
                        chart['labels'].append(result.get('label'))
                    chart['series'][i].append(result.get('count'))
        if item['type'] == 'total':
            db = web.database(dbn='sqlite', db=item['database'])
            results = db.query(item['sql'])
            totals = []
            total = 0
            for result in results:
                total += result.get('count')
                totals.append({
                    'label': result.get('label'),
                    'count': result.get('count'),
                    'total': total
                })
            chart['series'].append([])
            for t in totals:
                chart['labels'].append(t.get('label'))
                chart['series'][i].append(t.get('total'))
            if item.get('limit'):
                chart['labels'] = chart['labels'][-item['limit']:]
                chart['series'][i] = chart['series'][0][-item['limit']:]
    if raw.get('label'):
        chart['labels'] = [globals()[raw['label']](label) for label in chart['labels']]
    if raw.get('name') == "progress":
        chart['series'][0] -= chart['series'][1]
    return chart

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
        updated=now, finished=finished,
        annotation=json.dumps(data)
    )
    
def savetranscription(uid, pkey, data):
    project = yaml.load(open('projects/' + pkey + '.yaml'))
    pdb = web.database(dbn='sqlite', db=project['source']['database'])

    finished = True
    if data.pop('skip', False):
        raise web.seeother("%s/project/telemark" % config['prefix'])
    if data.pop('later', False):
        finished = False
    now = str(datetime.date.today())
    key = data[project['key']]
    id = str(uuid.uuid4())
    db.insert('transcriptions',
        id=id, project=pkey, key=key, user=uid, date=now, finished=finished,
        updated=now, annotation=json.dumps(data)
    )
    where = dict(occurrenceID=key)
    if finished:
        pdb.update(project['source']['table'], where=web.db.sqlwhere(where),
                completed = web.db.SQLLiteral("completed + 1"))

class index:
    def GET(self):
        changelog = []
        with open('changelog') as log:
            changes = list(islice(log, 50))
        for change in changes:
            m = re.match(r"(?P<date>.+):\s*(?P<text>.*)\s*\((?P<project>.*)\)",
                    change)
            if m: changelog.append(m.groupdict())
        projects = []
        for f in glob.glob("projects/*.yaml"):
            if not os.path.basename(f) in config.get('hidden', []):
                projects.append(yaml.load(open(f)))
        return render.index(projects, changelog)

class bakrom:
    def GET(self, key=None):
        if not session.get('admin'): return web.seeother("%s" % prefix)
        return render.bakrom(key)

class help:
    def GET(self, key=None):
        project = config
        if key:
            project = yaml.load(open('projects/' + key + '.yaml'))
        forms = OrderedDict((form, project['forms'][form]) for form in project['annotate']['order'])
        if 'pdf' in web.input():
          # pdfkit.from_string(render.help(project, forms), 'static/help.pdf')
          return web.seeother('%s/static/help.pdf' % prefix)
        return render.help(project, forms, key, project)

class unfinished:
    def GET(self, id):
        uid = session.get('id')
        nick = session.get('name', "Anonym")
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
            return simplerender.transcribe("unfinished/" + record['id'], anno, forms, zoom, project, False, nick)
        except ValueError as e:
            raise web.seeother('%s/unfinished' % prefix)

    def POST(self, id):
        uid = session.get('id')
        updatetranscription(id, web.input())
        raise web.seeother("%s/unfinished" % prefix)


class listunfinished:
    def GET(self):
        uid = session.get('id')
        if not uid: raise web.seeother('%s' % prefix)
        reqs = { 'user': uid, 'finished': False }
        recs = db.select('transcriptions', order="updated DESC", where=web.db.sqlwhere(reqs))
        return render.list(recs)

class projectstats:
    def GET(self, key):
        uid = session.get('id')
        nick = session.get('name', "Anonym")
        project = yaml.load(open('projects/' + key + '.yaml'))
        stats = getstats(key, project)
        charts = []
        for item in project.get('bakrom', []):
            charts.append(chart(item))
        return render.stats(key, project, stats, charts)

class projectinfo:
    def GET(self, key):
        uid = session.get('id')
        nick = session.get('name', "Anonym")
        try:
            project = yaml.load(open('projects/' + key + '.yaml'))
            charts = []
            for item in project.get('stats', []):
                charts.append(chart(item))
            return render.projectinfo(key, project, charts)
        except IOError as e:
          raise web.seeother('%s' % prefix)

class suboccurrence:
    def GET(self, key, subkey, oid):
      uid = session.get('id')
      nick = session.get("name", "Anonym")
      data = web.input()
      try:
        project = yaml.load(open('projects/' + key + '.yaml'))
        pdb = web.database(dbn='sqlite', db=project['source']['database'])
        filters = {}
        if oid:
          q = { 'key': oid }
          recs = pdb.select(project['source']['table'], q, where="occurrenceID = $key", limit=1)
        else:
          if project['forms'].get('filter'):
            for f in project['forms']['filter']:
              if data.get(f['name']) and data[f['name']] != "None":
                filters[f['name']] = data[f['name']]
          if len(filters) < 1:
              where = "completed < 2"
          else:
              where = web.db.sqlwhere(filters)
          recs = pdb.select(project['source']['table'], where=where,
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
        return simplerender.transcribe("project/" + key, record, forms, zoom, project, True, nick)
      except IOError as e:
        raise web.seeother('%s' % prefix)
      except ValueError as e:
        raise web.seeother('%s' % prefix)

class subproject:
    def GET(self, key, subkey):
        uid = session.get('id')
        nick = session.get('name', "Anonym")
        project = yaml.load(open('projects/' + key + '.yaml'))
        pdb = web.database(dbn='sqlite', db=project['source']['database'])
        return simplerender.transcribe(key, record, forms, zoom, config, True, nick)

class project:
    def subprojects(self, key, uid, nick, data, project):
      pdb = web.database(dbn='sqlite', db=project['source']['database'])
      subprojects = pdb.query(project['subprojects']['query'])
      return render.subprojects(key, project, subprojects)

    def GET(self, key, oid=None):
      uid = session.get('id')
      nick = session.get("name", "Anonym")
      data = web.input()
      try:
        project = yaml.load(open('projects/' + key + '.yaml'))
        if 'subprojects' in project:
            return self.subprojects(key, uid, nick, data, project)
        pdb = web.database(dbn='sqlite', db=project['source']['database'])
        filters = {}
        if oid:
          q = { 'key': oid }
          recs = pdb.select(project['source']['table'], q, where="occurrenceID = $key", limit=1)
        else:
          if project['forms'].get('filter'):
            for f in project['forms']['filter']:
              if data.get(f['name']) and data[f['name']] != "None":
                filters[f['name']] = data[f['name']]
          if len(filters) < 1:
              where = "completed < 2"
          else:
              where = web.db.sqlwhere(filters)
          recs = pdb.select(project['source']['table'], where=where,
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
        return simplerender.transcribe("project/" + key, record, forms, zoom, project, True, nick)
      except IOError as e:
        raise web.seeother('%s' % prefix)
      except ValueError as e:
        raise web.seeother('%s' % prefix)

    def POST(self, pkey):
        uid = session.get('id')
        savetranscription(uid, pkey, web.input())
        referer = web.ctx.env.get('HTTP_REFERER', '%s' % prefix)
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
        nick = session.get("name", "Anonym")
        key = key.replace("urn:catalog:", "")
        url = "%s%s.json" % (RESOLVER, key)
        try:
          raw = json.loads(urllib2.urlopen(url).read())
          record = {}
          for k,v in raw.iteritems():
            record[k.replace("dwc:", "")] = v
          date = record.get('eventDate')
          zoom = zoomify(record['associatedMedia'])
          if date:
            record['year'], record['month'], record['day'] = date.split("-")
          forms = OrderedDict((form, buildform(form, config)) for form in config['annotate']['order'])
          for _, form in forms.iteritems(): form.validates(record)
          return simplerender.transcribe(key, record, forms, zoom, config, True, nick)
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
        raise web.seeother('%s/annotation/%s' % id)

urls = (
    '%s' % prefix, 'index',
    '%s/' % prefix, 'index',

    '%s/hjelp' % prefix, 'help',
    '%s/help' % prefix, 'help',

    '%s/bakrom' % prefix, 'bakrom',
    '%s/backroom' % prefix, 'bakrom',

    '%s/uferdig' % prefix, 'listunfinished',
    '%s/uferdig/(.+)' % prefix, 'unfinished',

    '%s/unfinished' % prefix, 'listunfinished',
    '%s/unfinished/(.+)' % prefix, 'unfinished',


    '%s/prosjekt/(.+)/sub-(.+)/(.+)' % prefix, 'suboccurrence',
    '%s/prosjekt/(.+)/sub-(.+)' % prefix, 'subproject',
    '%s/prosjekt/(.+)/info' % prefix, 'projectinfo',
    '%s/prosjekt/(.+)/log' % prefix, 'projectlog',
    '%s/prosjekt/(.+)/bakrom' % prefix, 'projectstats',
    '%s/prosjekt/(.+)/help' % prefix, 'help',
    '%s/prosjekt/(.+)/(.+)' % prefix, 'project',
    '%s/prosjekt/(.+)/' % prefix, 'project',
    '%s/prosjekt/(.+)' % prefix, 'project',

    '%s/project/(.+)/sub-(.+)/(.+)' % prefix, 'suboccurrence',
    '%s/project/(.+)/sub-(.+)' % prefix, 'subproject',
    '%s/project/(.+)/info' % prefix, 'projectinfo',
    '%s/project/(.+)/log' % prefix, 'projectlog',
    '%s/project/(.+)/backroom' % prefix, 'projectstats',
    '%s/project/(.+)/help' % prefix, 'help',
    '%s/project/(.+)/(.+)' % prefix, 'project',
    '%s/project/(.+)/' % prefix, 'project',
    '%s/project/(.+)' % prefix, 'project',

    '%s/annotation/(.+)' % prefix, 'showannotation',
    '%s/annotations/(.+)' % prefix, 'showannotations',

    '%s/(.+)' % prefix, 'annotate',
)

languages = ['en_US', "nb_NO"]
gettext.install('messages', 'lang', unicode=True)
for lang in languages:
    gettext.translation('messages', 'lang', languages = [lang]).install(True)

web.config.session_parameters['timeout'] = 2592000
web.config.session_parameters['cookie_domain'] = "data.gbif.no"
web.config.session_parameters['cookie_path'] = "/"

# Monkey patch for å få sessions til å vare
def toughcookie(self):
  if not self.get('_killed'):
    self._setcookie(self.session_id, expires=31536000)
    self.store[self.session_id] = dict(self._data)
  else:
    self._setcookie(self.session_id, expires=-1)
web.session.Session._save = toughcookie


app = web.application(urls, locals())
session = web.session.Session(app, web.session.DiskStore(config.get('sessions', 'sessions')))

simplerender = template.render('templates', globals= {
    '_': _,
    'prefix': prefix,
    'json': json,
    'helper': helpers(),
    'web': web,
    'config': config
})

render = template.render('templates', base='layout', globals= {
    '_': _,
    'prefix': prefix,
    'json': json,
    'helper': helpers(),
    'web': web,
    'config': config,
    'crumbs': crumbs
})

web.config.debug = True

if __name__ == "__main__":
    app.run()

