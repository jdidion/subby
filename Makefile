module = subby
version = 0.1.7
repo = jdidion/$(module)
desc = Release $(version)
tests = tests
pytestopts = -s -vv --show-capture=all

all: clean install test

install: clean
	poetry build
	pip install --upgrade dist/$(module)-$(version)-py3-none-any.whl $(installargs)

test:
	env PYTHONPATH="." coverage run -m pytest -p pytester $(pytestopts) $(tests)
	coverage report -m
	coverage xml

docs:
	make -C docs api
	make -C docs html

lint:
	pylint $(module)

clean:
	rm -Rf __pycache__
	rm -Rf **/__pycache__/*
	rm -Rf **/*.c
	rm -Rf **/*.so
	rm -Rf **/*.pyc
	rm -Rf dist
	rm -Rf build
	rm -Rf $(module).egg-info

tag:
	git tag $(version)

push_tag:
	git push origin --tags

del_tag:
	git tag -d $(version)

pypi_release:
	poetry publish

release: clean tag
	${MAKE} install test pypi_release push_tag || (${MAKE} del_tag && exit 1)

	curl -v -i -X POST \
		-H "Content-Type:application/json" \
		-H "Authorization: token $(token)" \
		https://api.github.com/repos/$(repo)/releases \
		-d '{"tag_name":"$(version)","target_commitish": "master","name": "$(version)","body": "$(desc)","draft": false,"prerelease": false}'
