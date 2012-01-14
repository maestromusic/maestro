#!/bin/sh
echo running pyrcc4 for OMG\'s images
pyrcc4 -py3 -o omg/resources.py images/images.qrc
for plugin in omg/plugins/*/; do
  if [ -f $plugin/resources.qrc ]; then
    echo running pyrcc4 for $plugin
    pyrcc4 -py3 $plugin/resources.qrc -o $plugin/resources.py
  fi
done
