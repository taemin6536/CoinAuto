.PHONY: help install install-dev test test-unit test-property test-integration lint format type-check security-check clean run

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install production dependencies
	pip install -r requirements.txt

install-dev:  ## Install development dependencies
	pip install -r requirements-dev.txt
	pre-commit install

test:  ## Run all tests
	pytest

test-unit:  ## Run unit tests only
	pytest tests/unit/

test-property:  ## Run property-based tests only
	pytest tests/property/ -m property

test-integration:  ## Run integration tests only
	pytest tests/integration/ -m integration

test-coverage:  ## Run tests with coverage report
	pytest --cov=upbit_trading_bot --cov-report=html --cov-report=term

lint:  ## Run linting checks
	flake8 upbit_trading_bot tests
	bandit -r upbit_trading_bot

format:  ## Format code
	black upbit_trading_bot tests
	isort upbit_trading_bot tests

type-check:  ## Run type checking
	mypy upbit_trading_bot

security-check:  ## Run security checks
	bandit -r upbit_trading_bot
	safety check

quality-check:  ## Run all quality checks
	$(MAKE) format
	$(MAKE) lint
	$(MAKE) type-check
	$(MAKE) security-check

clean:  ## Clean up generated files
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/

run:  ## Run the trading bot
	python -m upbit_trading_bot.main

setup-venv:  ## Set up virtual environment
	python -m venv venv
	@echo "Virtual environment created. Activate with:"
	@echo "source venv/bin/activate  # On Linux/Mac"
	@echo "venv\\Scripts\\activate     # On Windows"

init-db:  ## Initialize database
	python -m upbit_trading_bot.database.init_db

docker-build:  ## Build Docker image
	docker build -t upbit-trading-bot .

docker-run:  ## Run Docker container
	docker run --env-file .env -v $(PWD)/config:/app/config upbit-trading-bot