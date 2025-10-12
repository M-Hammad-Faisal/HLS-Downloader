.PHONY: help install install-dev format lint type-check test clean all

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install production dependencies
	pip install -r requirements.txt
	playwright install chromium

install-dev:  ## Install development dependencies
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	playwright install chromium
	pre-commit install

format:  ## Format code with Black and isort
	black videodownloader/
	isort videodownloader/

lint:  ## Run linting with flake8
	flake8 videodownloader/

type-check:  ## Run type checking with mypy
	mypy videodownloader/

test:  ## Run tests with pytest
	pytest

prettier:  ## Format JSON/YAML files with Prettier
	npx prettier --write "*.json" "*.yml" "*.yaml"

pre-commit:  ## Run pre-commit hooks on all files
	pre-commit run --all-files

build:  ## Build executable for current platform
	python build_executable.py

build-clean:  ## Clean build directories and rebuild
	python build_executable.py --clean
	python build_executable.py

clean:  ## Clean up cache and build files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/ dist/ .mypy_cache/ .pytest_cache/ htmlcov/ release/
	rm -f *.spec

clean-all: clean  ## Clean everything including build artifacts
	rm -rf release/

all: format lint type-check test  ## Run all quality checks

check: lint type-check  ## Run linting and type checking only