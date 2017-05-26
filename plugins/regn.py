import metnopy

from yapsy.IPlugin import IPlugin
from dugnadplugins import *

class regn(IChartPlugin):
    def name(self):
        return "regn"

    def chart(self, chart, raw, series):
        chart['series'][series].append(24)
        w = {}
        a = raw['_from']
        b = raw['_to']
        data = metnopy.get_met_data("2", "30255", "RA", a, b, "12", "")
        for term, dates in data.iteritems():
            for ts, v in dates.iteritems():
                date = ts.to_pydatetime().strftime("%Y-%m-%d")
                w[date] = v
        for date in w:
            if date in chart['labels']: chart['series'][series].append(w[date])
        return chart

