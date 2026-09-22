PYTHON ?= python3
VENV ?= .venv
PY := $(VENV)/bin/python
HOST ?= 0.0.0.0
PORT ?= 8000

.PHONY: setup run test reset check

## setup: create venv, install deps, migrate, seed demo data if the DB is empty (safe to re-run)
setup:
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q -r requirements.txt
	$(PY) manage.py migrate --noinput
	$(PY) manage.py seed_demo

## run: start the dev server (does NOT erase data)
run:
	$(PY) manage.py migrate --noinput
	$(PY) manage.py seed_demo
	$(PY) manage.py runserver --insecure $(HOST):$(PORT)

## test: run the server-side test suite against an isolated in-memory database
test:
	$(PY) manage.py test -v 2

## reset: explicitly wipe demo records and re-seed deterministic data
reset:
	$(PY) manage.py seed_demo --reset

## check: Django system checks
check:
	$(PY) manage.py check
