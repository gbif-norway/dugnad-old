#!/usr/bin/python

import sys
import sqlite3
import unicodecsv

db = sqlite3.connect("projects.db")

reader = unicodecsv.DictReader(open("data-19-09-2017.csv"), delimiter='\t')
for row in reader:
    db.execute("insert into fossil values(?, ?, ?, ?, ?, ?);",
            (row['catalogNumber'], row['placement'], row['placementRemarks'],
             row['url'], row['generalRemarks'], 0))
db.commit()

