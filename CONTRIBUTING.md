# Contributing

Thanks for your interest! This is a small learning project, but contributions are welcome.

1. Fork the repo and create a branch: `git checkout -b my-change`.
2. Set up: `pip install -e ".[dev]"` (optionally `pre-commit install`).
3. Make your change and add a test for it. Tests must not need the internet – use `tests/fakesite.py`.
4. Run `make check` (ruff, mypy, pytest). CI runs the same on Linux and Windows.
5. Open a pull request describing what changed and why. Add a line to `CHANGELOG.md`.

Please keep the scraper polite: no changes that bypass `robots.txt` or the rate limiter by default.
