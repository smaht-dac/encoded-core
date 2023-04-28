SHELL=/bin/bash

configure:
	pip install poetry==1.3.2

build:
	poetry install

info:
	@: $(info Here are some 'make' options:)
	   $(info - Use 'make configure' to download a working poetry version.)
	   $(info - Use 'make build' to build only application dependencies.)
