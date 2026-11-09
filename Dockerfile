FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY webscraper ./webscraper
RUN pip install --no-cache-dir ".[excel]" && useradd --create-home scraper

USER scraper
WORKDIR /data
ENTRYPOINT ["webscraper"]
CMD ["--help"]
