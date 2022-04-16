#!/bin/sh
pip install --no-cache-dir -r ./src/volume/requirements.txt
cd ./src
# python ./app.py
export FLASK_APP=app.py
flask run
