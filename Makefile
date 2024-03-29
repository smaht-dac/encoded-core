SHELL=/bin/bash

configure:
	pip install poetry==1.4.2

build:
	make configure
	poetry install

test-any:
	poetry run python -m pytest -xvv -r w --timeout=200

test:
	make test-any

publish:
	poetry run publish-to-pypi

publish-for-ga:
	poetry install
	poetry run publish-to-pypi --noconfirm

remote-test:
	poetry run python -m pytest -xvv -r w --timeout=200 --es search-fourfront-testing-opensearch-kqm7pliix4wgiu4druk2indorq.us-east-1.es.amazonaws.com:443

info:
	@: $(info Here are some 'make' options:)
	   $(info - Use 'make configure' to download a working poetry version.)
	   $(info - Use 'make build' to build only application dependencies.)
