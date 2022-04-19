#!/bin/sh
pip install --no-cache-dir -r ./src/volume/requirements.txt
cd ./src
python ./app.py
