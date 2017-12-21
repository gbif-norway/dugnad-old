#!/bin/bash

[ -z $2 ] && exit

pages=$(qpdf --show-npages $1)

for page in $(seq 1 $pages); do
  echo "Generating dzi for page $page"
  vips pdfload --page $page --dpi 240 $1 $2/$page.tif
  vips dzsave $2/$page.tif $2/$page.dzi
done

