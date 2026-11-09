.PHONY: install test lint typecheck check run clean

install:
	pip install -e ".[dev]"

test:
	pytest --cov=webscraper

lint:
	ruff check .

typecheck:
	mypy webscraper

check: lint typecheck test

run:
	python -m webscraper scrape --max-pages 2 --details -o output/books.csv -o output/report.html

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov .webscraper_cache
