module = subby
version = 0.1.3
repo = jdidion/$(module)
desc = Release $(version)
tests = tests
pytestopts = -s -vv --show-capture=all

BUILD = poetry build && pip install --upgrade dist/$(module)-$(version)-py3-none-any.whl $(installargs)
TEST  = env PYTHONPATH="." coverage run -m pytest -p pytester $(pytestopts) $(tests) && coverage report -m && coverage xml

all:
	$(clean)
	$(BUILD)
	$(TEST)

install:
	$(BUILD)

test:
	$(TEST)

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

release:
	$(clean)
	# tag
	git tag $(version)
	# build
	$(BUILD)
	$(TEST)
	# release
	poetry publish
	git push origin --tags
	$(github_release)

github_release:
	curl -v -i -X POST \
		-H "Content-Type:application/json" \
		-H "Authorization: token $(token)" \
		https://api.github.com/repos/$(repo)/releases \
		-d '{"tag_name":"$(version)","target_commitish": "master","name": "$(version)","body": "$(desc)","draft": false,"prerelease": false}'
