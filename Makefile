SHELL=/bin/bash

configure:
	pip install poetry==1.3.2

build:
	poetry install

test-any:
	poetry run python -m pytest -xvv -r w --timeout=200

test:
	make test-any

info:
	@: $(info Here are some 'make' options:)
	   $(info - Use 'make configure' to download a working poetry version.)
	   $(info - Use 'make build' to build only application dependencies.)
