#!/usr/bin/env bash

# This command runs Gunicorn, binding it to the port defined by Render's environment variable.
# 'app:app' means run the Flask app instance named 'app' from the file 'app.py'.
gunicorn --bind 0.0.0.0:$PORT app:app