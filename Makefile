build:
	uv build
publish-test:
	uvx twine upload --repository testpypi dist/* --verbose
publish:
	uvx twine upload dist/* --verbose
clean:
	rm -rf dist build *.egg-info
