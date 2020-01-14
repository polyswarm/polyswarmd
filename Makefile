.PHONY: clean clean-test clean-pyc clean-build help
.DEFAULT_GOAL := help
SRCROOT := src/polyswarmd

help:
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

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

lint: ## check style
	-mypy
	-flake8 $(SRCROOT)
	-yapf -p -r -d $(SRCROOT)
	-isort --recursive --diff $(SRCROOT)

format:  ## format code in Polyswarm style
	yapf -p -r -i $(SRCROOT)
	isort --recursive $(SRCROOT)

genstubs: # generate websocket event definition type stubs
	python -m websockets.scripts.gen_stubs | yapf

test: ## run tests
	POLY_WORK=testing py.test

coverage: ## check code coverage
	coverage run --source $(SRCROOT) -m pytest
	coverage report -m
	coverage html
	$(BROWSER) htmlcov/index.html
