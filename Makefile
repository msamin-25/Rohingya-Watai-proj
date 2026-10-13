# Rohingya Voice Interpreter - common tasks (macOS / Linux).
# On Windows without make, run the commands under each target by hand (see README).

PY  ?= .venv/bin/python
VENV ?= .venv

.PHONY: setup venv install build env test test-ml test-backend test-frontend run eval e2e audit check-dist

setup: venv install build env  ## everything needed to run the app

venv:
	@# On an iCloud-synced folder (macOS Desktop/Documents) keep the real venv in .venv.nosync,
	@# which iCloud skips, and link .venv to it.
	test -e $(VENV) || (python3 -m venv $(VENV).nosync && ln -s $(VENV).nosync $(VENV))

install:
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e "ml[dev,llm]" -r backend/requirements-dev.txt
	@# macOS can flag .pth files as hidden, which Python 3.13 then ignores.
	-@[ "$$(uname)" = "Darwin" ] && chflags nohidden $(VENV)/lib/python3*/site-packages/*.pth 2>/dev/null || true
	cd frontend && npm ci

build:
	cd frontend && npm run build

env:
	$(PY) scripts/make_env.py

test: test-ml test-backend test-frontend

test-ml:
	cd ml && ../$(PY) -m pytest -q

test-backend:
	cd backend && ../$(PY) -m pytest -q

test-frontend:
	cd frontend && npm test

run:
	cd backend && ../$(PY) -m uvicorn app.main:factory --factory --reload --port 8000

eval:  ## make eval DIR=~/rvb-eval/recordings
	$(PY) -m rvb_ai.eval_matcher $(DIR)

e2e:
	cd e2e && npm ci && npx playwright install chromium && npx playwright test

audit:
	$(PY) -m pip_audit --skip-editable -r backend/requirements.txt
	cd frontend && npm audit

check-dist: build
	git diff --exit-code -- frontend/dist
