.PHONY: clean clean-test clean-pyc clean-build help
.DEFAULT_GOAL := help
SRCROOT := src/polyswarmd
TESTSRCROOT := tests/

define PRINT_HELP_PYSCRIPT
import re, sys
for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

help:
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

lint: doctest mypy ## check style
# static checks
	-flake8 $(SRCROOT)
# style checks
	-yapf -p -r -d $(SRCROOT)
# order import
	-isort --recursive --diff $(SRCROOT)
# verify that requirements.txt is ordered
	sort -u -c requirements.txt && sort -u -c requirements.dev.txt

mypy:  ## check types
	mypy

format: format-requirements format-tests ## format code in Polyswarm style
	yapf -p -r -i $(SRCROOT)
	isort --recursive $(SRCROOT)

format-tests:  ## format test code in Polyswarm style
	yapf -p -r -i  --exclude tests/test_suite_internals.py $(TESTSRCROOT)
	isort --recursive $(TESTSRCROOT)

format-requirements:  ## sort requirements.txt
	sort -u requirements.txt -o requirements.txt
	sort -u requirements.dev.txt -o requirements.dev.txt

msgstubs: # generate websocket event definition type stubs
	(cd $(SRCROOT) && python -m websockets.scripts.gen_stubs | yapf)

doctest: ## run doctests
	(cd $(SRCROOT) && python -m websockets)

test: doctest ## run tests
	py.test

clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/

	find . \( -path ./env -o -path ./venv -o -path ./.env -o -path ./.venv \) -prune -o -name '*.egg-info' -exec rm -fr {} +
	find . \( -path ./env -o -path ./venv -o -path ./.env -o -path ./.venv \) -prune -o -name '*.egg' -exec rm -f {} +

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test: ## remove test and coverage artifacts
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache

coverage: ## check code coverage
	coverage run --source $(SRCROOT) -m pytest
	coverage report -m
	coverage html
	$(BROWSER) htmlcov/index.html
