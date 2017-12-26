#!/usr/bin/python
# coding: utf-8

VERSION = "0.5.0"

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
import random
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

RESOLVER = "https://data.gbif.no/resolver/"

logging.basicConfig(level=logging.INFO)

manager = PluginManager()
manager.setCategoriesFilter({
    'Chart': IChartPlugin
})
manager.setPluginPlaces(["plugins"])
manager.collectPlugins()
config = yaml.load(file('config.yaml'))
prefix = re.search(r"http?s:\/\/[^\/]+(.*)", config['prefix']).groups()[0]
db = web.database(dbn='sqlite', db='dugnad.db')

def loadproject(key):
  p = yaml.load(open('projects/' + key + '.yaml'))
  p['_key'] = key
  return p

try:
    from gi.repository import Vips
    config['zoom'] = True
except ImportError:
    config['zoom'] = False

def user():
  return web.ctx.user

def crumbs():
    if not 'crumbs' in web.ctx: web.ctx['crumbs'] = []
    return web.ctx['crumbs']

class HelpBox(object):
    def __init__(self, text):
        self.text = text

    def name(self):
        return text

class helpers:
  def name(self):
    return web.ctx.nick

  def uid(self):
    return web.ctx.uid

  def admin(self):
    return web.ctx.isadmin

  def showfilter(self, config):
    if 'filter' in config:
        form = buildform('filter', config)
        form.validates(web.input())
        return form

# flytt dette til config
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
    link = "<a class=help title='%s'>" % _(text)
    link += "<img src='%s/images/help.png'>" % config['base']
    link += "</a>"
    return link

def validaterecord(db, data, project, oid=None):
    record = getrecord(db, data, project, oid)
    forms = OrderedDict((form, buildform(form, project)) for form in project['annotate']['order'])
    for _, form in forms.iteritems(): form.validates(record)
    return (record, forms)

def getrecord(db, data, project, oid=None):
  if not db: return {}
  filters = {}
  if oid:
    q = { 'key': oid }
    where = "%s = $key" % project['key']
    recs = db.select(project['source']['table'], q, where=where, limit=1)
  else:
    if project['forms'].get('filter'):
      for f in project['forms']['filter']:
        if data.get(f['name']) and data[f['name']] != "None":
          filters[f['name']] = data[f['name']]
    if len(filters) < 1:
        where = "completed < 2"
    else:
        where = web.db.sqlwhere(filters)
    recs = db.select(project['source']['table'],
            where=where, limit=200, order="priority DESC")
  try:
    records = []
    for rec in recs: records.append(rec)
    record = random.choice(records)

    record['_zoom'] = zoomify(record.get('associatedMedia'))
    record['_id'] = record[project['key']]
    return record
  except IndexError as e:
    return None

def buildform(key, config):
    if not key in config['forms']: raise Exception("Form not found")
    inputs = []
    for i in config['forms'][key]:
        if not 'name' in i: raise Exception("Needs a name")
        if not 'type' in i: raise Exception("Needs a type")
        k = i['name']
        if i['type'] == "text":
            opts = {}
            opts['description'] = _(k)
            opts['post'] = helplink(i.get('help'))
            if 'disabled' in i or 'readonly' in i:
                opts['readonly'] = True
            if 'url' in i:
                opts['data-url'] = i['url']
            if 'pick' in i:
                opts['data-pick'] = i['pick'] = json.dumps(i['pick']) # ???
            inputs.append(form.Textbox(k, **opts))
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
              data = web.input()
              if 'match' in i:
                wheres = []
                for m in i['match']:
                  if data.get(m):
                    wheres.append("WHERE %s = %s" % (m, web.sqlquote(data[m])))
                query = i['sql'] % (" AND ".join(wheres))
              else:
                query = i['sql'] % ""
              results = [v.values()[0] for v in db.query(query)]
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
        elif i['type'] == 'location':
          inputs.append(form.Textbox("county", description = _('county'), readonly = True))
          inputs.append(form.Textarea("locality", description = _('locality'), readonly = True))
          inputs.append(form.Textbox("verbatimCoordinates", description = _('verbatimCoordinates'), readonly = True))
          inputs.append(form.Hidden("verbatimWKT", description = _('verbatimWKT'), readonly = True))
          inputs.append(form.Hidden("verbatimLatitude", description = _('verbatimLatitude'), readonly = True))
          inputs.append(form.Hidden("verbatimUncertaintyInMeters", description = _('verbatimUncertaintyInMeters'), readonly = True))
          inputs.append(form.Hidden("verbatimLongitude", description = _('verbatimLongitude'), readonly = True))
        elif i['type'] == "annotation":
          inputs.append(form.Hidden(k))
          inputs.append(form.Textbox(_('marked-pages'), readonly = True, id = "marked-pages"))
          inputs.append(form.Button(_("mark-page"), id = "mark-page"))
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
        if config['zoom']:
          name = "static/tmp/" + imagekey
          if not os.path.exists(name + "_files"):
            urllib.urlretrieve(source, "%s.jpg" % name)
            image = Vips.Image.new_from_file("%s.jpg" % name)
            image.dzsave(name, layout="dz")
          return "%s.dzi" % imagekey
    except Exception as e:
        return None

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
    project = loadproject(pkey)
    if 'database' in project['source']:
      pdb = web.database(dbn='sqlite', db=project['source']['database'])
    else:
      pdb = False

    finished = True
    if data.pop('skip', False):
        referer = web.ctx.env.get('HTTP_REFERER', '%s' % prefix)
        raise web.seeother(referer)
    if data.pop('later', False):
        finished = False
    now = str(datetime.date.today())
    if project['key'] == "_none":
      key = ""
    else:
      key = data[project['key']]
    if project.get('markings') and data['annotation']:
      pages = json.loads(data['annotation'])
      for page, markings in pages.iteritems():
        id = str(uuid.uuid4())
        db.insert('markings', id=id, project=pkey, page=page, markings=json.dumps(markings), user=uid, date=now)
    id = str(uuid.uuid4())
    db.insert('transcriptions',
        id=id, project=pkey, key=key, user=uid, date=now, finished=finished,
        updated=now, annotation=json.dumps(data)
    )
    where = dict()
    where[project['key']] = key
    if finished and pdb:
        pdb.update(project['source']['table'], where=web.db.sqlwhere(where),
                completed = web.db.SQLLiteral("completed + 1"))

class index:
    def GET(self):
        changelog = []
        with open('changelog') as log:
            changes = list(islice(log, 4))
        for change in changes:
            m = re.match(r"(?P<date>.+):\s*(?P<text>.*)\s*\((?P<project>.*)\)",
                    change)
            if m: changelog.append(m.groupdict())
        projects = []
        for f in glob.glob("projects/*.yaml"):
            if not os.path.basename(f) in config.get('hidden', []):
                data = yaml.load(open(f))
                data['slug'] = os.path.splitext(os.path.basename(f))[0]
                projects.append(data)
        return render.index(projects, changelog)

class bakrom:
    def GET(self, key=None):
        if not web.ctx.isadmin: return web.seeother("%s" % prefix)
        projects = []
        for f in glob.glob("projects/*.yaml"):
            if not os.path.basename(f) in config.get('hidden', []):
                data = yaml.load(open(f))
                data['slug'] = os.path.splitext(os.path.basename(f))[0]
                projects.append(data)
        return render.bakrom(key, projects)

class help:
    def GET(self, key=None):
        project = config
        if key:
            project = loadproject(key)
        forms = OrderedDict((form, project['forms'][form]) for form in project['annotate']['order'])
        if 'pdf' in web.input():
            return web.seeother('%s/static/help.pdf' % prefix)
        return render.help(project, forms, key, project)

class revise:
    def GET(self, id):
        nick = web.ctx.nick
        data = web.input()
        try:
            where = dict(id = id)
            recs = db.select('transcriptions', where = web.db.sqlwhere(where))
            record = recs[0]
            pkey = record['project']
            project = loadproject(record['project'])
            anno = json.loads(record['annotation'])
            if 'document' in project['source']:
              forms = OrderedDict((form, buildform(form, project)) for form in project['annotate']['order'])
              page = 1
              for _, form in forms.iteritems(): form.validates(anno)
              return simplerender.document('project/' + pkey, page, project, project['source'], forms)
            pdb = web.database(dbn='sqlite', db=project['source']['database'])
            origid = { project['key']: record['key'] }
            origs = pdb.select(project['source']['table'],
                where = web.db.sqlwhere(origid), limit=1)
            orig = origs[0]
            if orig.get("associatedMedia"):
                anno['_zoom'] = zoomify(orig['associatedMedia'])
            forms = OrderedDict((form, buildform(form, project)) for form in project['annotate']['order'])
            anno['_id'] = anno[project['key']]
            if record.get('finished'):
              anno['_finished'] = True
            for _, form in forms.iteritems(): form.validates(anno)
            return simplerender.transcribe("revise/" + record['id'], anno, forms, project, False, nick)
        except ValueError as e:
            raise web.seeother('%s/revised' % prefix)

    def POST(self, id):
        updatetranscription(id, web.input())
        raise web.seeother("%s/revise" % prefix)

class unfinished:
    def GET(self, id):
        nick = web.ctx.nick
        data = web.input()
        try:
            where = dict(id = id)
            recs = db.select('transcriptions', where = web.db.sqlwhere(where))
            record = recs[0]
            project = loadproject(record['project'])
            annoz = json.loads(record['annotation'])
            pdb = web.database(dbn='sqlite', db=project['source']['database'])
            origid = { project['key']: record['key'] }
            origs = pdb.select(project['source']['table'],
                where = web.db.sqlwhere(origid), limit=1)
            orig = origs[0]
            anno = orig.copy()
            anno.update(annoz)
            if orig.get("associatedMedia"):
                anno['_zoom'] = zoomify(orig['associatedMedia'])
            forms = OrderedDict((form, buildform(form, project)) for form in project['annotate']['order'])
            anno['_id'] = anno[project['key']]
            if record.get('finished'):
              anno['_finished'] = True
            for _, form in forms.iteritems(): form.validates(anno)
            return simplerender.transcribe("unfinished/" + record['id'], anno, forms, project, False, nick)
        except ValueError as e:
            raise web.seeother('%s/unfinished' % prefix)

    def POST(self, id):
        uid = web.ctx.uid
        updatetranscription(id, web.input())
        raise web.seeother("%s/unfinished" % prefix)

class changelog:
    def GET(self):
        changelog = []
        with open('changelog') as log:
            changes = list(log)
        for change in changes:
            m = re.match(r"(?P<date>.+):\s*(?P<text>.*)\s*\((?P<project>.*)\)",
                    change)
            if m: changelog.append(m.groupdict())
        return render.changelog(changelog)

class listfinished:
    def GET(self):
        uid = web.ctx.uid
        if not uid: raise web.seeother('%s' % prefix)
        reqs = { 'user': uid, 'finished': True }
        recs = db.select('transcriptions', order="updated DESC", where=web.db.sqlwhere(reqs), limit=10)
        return render.list("revise", recs)

class listunfinished:
    def GET(self):
        uid = web.ctx.uid
        if not uid: raise web.seeother('%s' % prefix)
        reqs = { 'user': uid, 'finished': False }
        recs = db.select('transcriptions', order="updated DESC", where=web.db.sqlwhere(reqs))
        return render.list("unfinished", recs)

class screencast:
    def GET(self, key):
        project = loadproject(key)
        return render.screencast(key, project)


class projectstats:
    def GET(self, key):
        uid = web.ctx.uid
        nick = web.ctx.nick
        project = loadproject(key)
        stats = getstats(key, project)
        charts = []
        for item in project.get('bakrom', []):
            charts.append(chart(item))
        return render.stats(key, project, stats, charts)

class projectinfo:
    def GET(self, key):
        uid = web.ctx.uid
        nick = web.ctx.nick
        try:
            project = loadproject(key)
            charts = []
            for item in project.get('stats', []):
                charts.append(chart(item))
            return render.projectinfo(key, project, charts)
        except IOError as e:
          raise web.seeother('%s' % prefix)

class project:
    def prefilter(self, prefilter, key, uid, nick, data, project):
      pdb = web.database(dbn='sqlite', db=project['source']['database'])
      rows = pdb.query(prefilter['list'])
      options = []
      for row in rows:
        row['complete'] = pdb.query(prefilter['complete'], vars={'id': row['key']})[0]['complete']
        options.append(row)
      return render.prefilter(key, project, options)

    def GET(self, key, oid=None):
      uid = web.ctx.uid
      nick = web.ctx.nick
      data = web.input()
      try:
        project = loadproject(key)
        if 'document' in project['source']:
          forms = OrderedDict((form, buildform(form, project)) for form in project['annotate']['order'])
          page = 1
          record, forms = validaterecord(None, data, project, oid)
          return simplerender.document('project/' + key, page, project, project['source'], forms)
        else:
          for prefilter in project.get('prefilters', []):
              if prefilter['name'] not in data:
                  return self.prefilter(prefilter, key, uid, nick, data, project)
          pdb = web.database(dbn='sqlite', db=project['source']['database'])
          record, forms = validaterecord(pdb, data, project, oid)
          return simplerender.transcribe("project/" + key, record, forms, project, True, nick)
      except IOError as e:
        raise web.seeother('%s' % prefix)
      except ValueError as e:
        raise web.seeother('%s' % prefix)

    def POST(self, pkey):
        project = loadproject(pkey)
        uid = web.ctx.uid
        savetranscription(uid, pkey, web.input())
        referer = web.ctx.env.get('HTTP_REFERER', '%s' % prefix)
        if 'sticky' in project:
          base = referer.split("?")[0]
          params = {}
          for k, v in web.input().iteritems():
            if k in project['sticky']: params[k] = v
          referer = base + "?" + urllib.urlencode(params)
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

class lookup:
  def GET(self, key):
    data = web.input()
    q = data.get('q')
    if q and key in config['lookup']:
      source = config['lookup'][key]
      where = { 'table': source['table'], 'key': source['key'], 'q': "%" + q + "%" }
      raw = db.query("SELECT * FROM " + source['table'] + " WHERE " + source['key'] + " LIKE $q LIMIT 20", vars=where)
      results = []
      for result in raw:
        results.append(result)
      return json.dumps(results)

class markings:
  def GET(self, key, page):
    project = loadproject(key)
    data = web.input()
    where = dict(page = page)
    raw = db.select('markings', where = web.db.sqlwhere(where))
    markings = []
    for m in raw:
      markings.append(json.loads(m['markings']))
    return json.dumps(markings)

class annotate:
    def GET(self, key):
        uid = web.ctx.uid
        nick = web.ctx.nick
        key = key.replace("urn:catalog:", "")
        url = "%s%s.json" % (RESOLVER, key)
        config['_key'] = "annotation"
        try:
          raw = json.loads(urllib2.urlopen(url).read())
          record = {}
          for k,v in raw.iteritems():
            record[k.replace("dwc:", "")] = v
          date = record.get('eventDate')
          record['_id'] = key
          record['_zoom'] = zoomify(record['associatedMedia'])
          if date:
            record['year'], record['month'], record['day'] = date.split("-")
          forms = OrderedDict((form, buildform(form, config)) for form in config['annotate']['order'])
          for _, form in forms.iteritems(): form.validates(record)
          return simplerender.transcribe(key, record, forms, config, True, nick)
        except Exception as e:
          message = "%s not found (%s)" % (key, e)
          return render.error(message)

    def POST(self, key):
        uid = web.ctx.uid
        key = key.replace("urn:catalog:", "")
        url = "%s%s.json" % (RESOLVER, key)
        data = web.input()
        record = json.loads(urllib2.urlopen(url).read())
        now = str(datetime.date.today())
        finished = True
        id = str(uuid.uuid4())
        if data.pop('finished', False):
          finished = False
        db.insert('annotations',
            id=id, key=key, user=uid, date=now, finished=finished,
            annotation=json.dumps(web.input()),
            original=json.dumps(record)
        )
            #'gbif-drift@nhm.uio.no', '[dugnad] ny annotering',
        web.sendmail('noreply@data.gbif.no',
            'christian.svindseth@nhm.uio.no', '[dugnad] ny annotering',
            "https://data.gbif.no/dugnad/annotation/%s / https://data.gbif.no/dugnad/annotations/%s" % (id, key))
        referer = web.ctx.env.get('HTTP_REFERER', '%s' % prefix)
        raise web.seeother(referer)

urls = (
    '%s' % prefix, 'index',
    '%s/' % prefix, 'index',

    '%s/changelog' % prefix, 'changelog',

    '%s/hjelp' % prefix, 'help',
    '%s/help' % prefix, 'help',

    '%s/bakrom' % prefix, 'bakrom',
    '%s/backroom' % prefix, 'bakrom',

    '%s/uferdig' % prefix, 'listunfinished',
    '%s/uferdig/(.+)' % prefix, 'unfinished',

    '%s/unfinished' % prefix, 'listunfinished',
    '%s/unfinished/(.+)' % prefix, 'unfinished',

    '%s/revider' % prefix, 'listfinished',
    '%s/revider/(.+)' % prefix, 'revise',

    '%s/revise' % prefix, 'listfinished',
    '%s/revise/(.+)' % prefix, 'revise',

    '%s/prosjekt/(.+)/screencast' % prefix, 'screencast',
    '%s/prosjekt/(.+)/info' % prefix, 'projectinfo',
    '%s/prosjekt/(.+)/log' % prefix, 'projectlog',
    '%s/prosjekt/(.+)/bakrom' % prefix, 'projectstats',
    '%s/prosjekt/(.+)/help' % prefix, 'help',
    '%s/prosjekt/(.+)/hjelp' % prefix, 'help',
    '%s/prosjekt/(.+)/markings/(.+)' % prefix, 'markings',
    '%s/prosjekt/(.+)/(.+)' % prefix, 'project',
    '%s/prosjekt/(.+)/' % prefix, 'project',
    '%s/prosjekt/(.+)' % prefix, 'project',

    '%s/project/(.+)/screencast' % prefix, 'screencast',
    '%s/project/(.+)/info' % prefix, 'projectinfo',
    '%s/project/(.+)/log' % prefix, 'projectlog',
    '%s/project/(.+)/backroom' % prefix, 'projectstats',
    '%s/project/(.+)/help' % prefix, 'help',
    '%s/project/(.+)/hjelp' % prefix, 'help',
    '%s/project/(.+)/markings/(.+)' % prefix, 'markings',
    '%s/project/(.+)/(.+)' % prefix, 'project',
    '%s/project/(.+)/' % prefix, 'project',
    '%s/project/(.+)' % prefix, 'project',

    '%s/annotering/(.+)' % prefix, 'showannotation',
    '%s/annoteringer/(.+)' % prefix, 'showannotations',

    '%s/annotation/(.+)' % prefix, 'showannotation',
    '%s/annotations/(.+)' % prefix, 'showannotations',

    '%s/lookup/(.+)' % prefix, 'lookup',

    '%s/(.+)' % prefix, 'annotate',
)

languages = ["en_US", "nb_NO"]
gettext.install('messages', 'lang', unicode=True)
for lang in languages:
    gettext.translation('messages', 'lang', languages = [lang]).install(True)

web.config.session_parameters['timeout'] = 2592000
web.config.session_parameters['cookie_domain'] = "data.gbif.no"
web.config.session_parameters['cookie_path'] = "/"

# monkey patch for å få sessions til å vare
def toughcookie(self):
  if not self.get('_killed'):
    self._setcookie(self.session_id, expires=31536000)
    self.store[self.session_id] = dict(self._data)
  else:
    self._setcookie(self.session_id, expires=-1)
web.session.Session._save = toughcookie

app = web.application(urls, locals())
session = web.session.Session(app, web.session.DiskStore(config.get('sessions', 'sessions')))

simplerender = template.render('templates', globals={
    '_': _,
    'prefix': prefix,
    'json': json,
    'helper': helpers(),
    'web': web,
    'config': config,
    'crumbs': crumbs,
    'version': VERSION
})

render = template.render('templates', base='layout', globals={
    '_': _,
    'prefix': prefix,
    'json': json,
    'helper': helpers(),
    'web': web,
    'config': config,
    'crumbs': crumbs,
    'version': VERSION
})

def login():
  web.ctx.uid = 1 # session.get('id')
  web.ctx.nick = "bie" # session.get('name', "Anonym")
  web.ctx.isadmin = True # session.get('admin')

app.add_processor(web.loadhook(login))

web.config.debug = True

if __name__ == "__main__":
    app.run()

