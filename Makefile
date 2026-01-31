.PHONY: help install install-dev build clean clean-venv reset test lint format check publish-test publish version bump-patch bump-minor bump-major setup dev-install

# Colors for terminal output
BLUE := \033[34m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
RESET := \033[0m

# Package info
PACKAGE_NAME := openbotx
VERSION := $(shell uv run python -c "from openbotx.version import __version__; print(__version__)" 2>/dev/null || echo "0.0.0")

help: ## Show this help message
	@echo "$(BLUE)OpenBotX — Personal AI Assistant$(RESET)"
	@echo ""
	@echo "$(GREEN)Usage:$(RESET)"
	@echo "  make $(YELLOW)<target>$(RESET)"
	@echo ""
	@echo "$(GREEN)Quick Start (Development):$(RESET)"
	@echo "  make $(YELLOW)setup$(RESET)        - First time setup (creates venv + installs deps)"
	@echo "  make $(YELLOW)dev-install$(RESET)  - Install in editable mode for development"
	@echo ""
	@echo "$(GREEN)All Targets:$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-15s$(RESET) %s\n", $$1, $$2}'

# ============================================================================
# Development Setup (START HERE)
# ============================================================================

setup: ## First time setup: create venv and install in dev mode with uv
	@echo "$(BLUE)Setting up development environment with uv...$(RESET)"
	@if [ ! -d ".venv" ]; then \
		echo "$(GREEN)Creating virtual environment with uv...$(RESET)"; \
		uv venv .venv; \
	fi
	@echo "$(GREEN)Installing package in editable mode with dev dependencies...$(RESET)"
	uv pip install -e ".[dev]"
	@echo ""
	@echo "$(GREEN)Setup complete!$(RESET)"
	@echo "$(YELLOW)Activate the virtual environment with:$(RESET)"
	@echo "  source .venv/bin/activate"

dev-install: ## Install in editable mode (use during development)
	@echo "$(BLUE)Installing in editable (development) mode with uv...$(RESET)"
	uv pip install -e ".[dev]"
	@echo "$(GREEN)Installed! Changes to code will take effect immediately.$(RESET)"

# ============================================================================
# Installation
# ============================================================================

install: ## Install package in production mode
	uv pip install .

install-dev: dev-install ## Alias for dev-install

# ============================================================================
# Building
# ============================================================================

build: clean ## Build the package
	@echo "$(BLUE)Building package...$(RESET)"
	uv run python -m build
	@echo "$(GREEN)Build complete! Packages in dist/$(RESET)"

clean: ## Clean build artifacts
	@echo "$(BLUE)Cleaning build artifacts...$(RESET)"
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf openbotx.egg-info/
	rm -rf .eggs/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	@echo "$(GREEN)Clean complete!$(RESET)"

clean-venv: ## Remove virtual environment
	@echo "$(BLUE)Removing virtual environment...$(RESET)"
	rm -rf .venv/
	@echo "$(GREEN)Virtual environment removed!$(RESET)"

reset: clean-venv setup ## Reset environment (remove venv and setup again)

# ============================================================================
# Testing
# ============================================================================

test: ## Run tests
	@echo "$(BLUE)Running tests...$(RESET)"
	uv run pytest tests/ -v

test-cov: ## Run tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(RESET)"
	uv run pytest tests/ -v --cov=openbotx --cov-report=html --cov-report=term-missing

# ============================================================================
# Code quality
# ============================================================================

lint: ## Run linter (ruff)
	@echo "$(BLUE)Running linter...$(RESET)"
	uv run ruff check openbotx/

format: ## Format code (ruff)
	@echo "$(BLUE)Formatting code...$(RESET)"
	uv run ruff format openbotx/
	uv run ruff check --fix openbotx/

check: lint ## Run all checks (lint + type check)
	@echo "$(BLUE)Running type checker...$(RESET)"
	uv run mypy openbotx/

# ============================================================================
# Publishing
# ============================================================================

publish-test: build ## Publish to TestPyPI
	@echo "$(BLUE)Publishing to TestPyPI...$(RESET)"
	@echo "$(YELLOW)Make sure you have configured ~/.pypirc with testpypi credentials$(RESET)"
	uv run python -m twine upload --repository testpypi dist/*
	@echo "$(GREEN)Published to TestPyPI!$(RESET)"
	@echo "$(YELLOW)Install with: uv pip install --index-url https://test.pypi.org/simple/ openbotx$(RESET)"

publish: build ## Publish to PyPI (production)
	@echo "$(RED)WARNING: This will publish to PyPI (production)!$(RESET)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	@echo "$(BLUE)Publishing to PyPI...$(RESET)"
	uv run python -m twine upload dist/*
	@echo "$(GREEN)Published to PyPI!$(RESET)"
	@echo "$(YELLOW)Install with: uv pip install openbotx$(RESET)"

# ============================================================================
# Versioning
# ============================================================================

version: ## Show current version
	@echo "$(BLUE)Current version:$(RESET) $(VERSION)"

bump-patch: ## Bump patch version (0.0.X)
	@echo "$(BLUE)Bumping patch version...$(RESET)"
	@uv run python -c "import re; \
		v = '$(VERSION)'.split('.'); \
		v[2] = str(int(v[2]) + 1); \
		new_v = '.'.join(v); \
		content = open('openbotx/version.py').read(); \
		content = re.sub(r'__version__ = \".*\"', f'__version__ = \"{new_v}\"', content); \
		open('openbotx/version.py', 'w').write(content); \
		print(f'Version bumped to {new_v}')"

bump-minor: ## Bump minor version (0.X.0)
	@echo "$(BLUE)Bumping minor version...$(RESET)"
	@uv run python -c "import re; \
		v = '$(VERSION)'.split('.'); \
		v[1] = str(int(v[1]) + 1); \
		v[2] = '0'; \
		new_v = '.'.join(v); \
		content = open('openbotx/version.py').read(); \
		content = re.sub(r'__version__ = \".*\"', f'__version__ = \"{new_v}\"', content); \
		open('openbotx/version.py', 'w').write(content); \
		print(f'Version bumped to {new_v}')"

bump-major: ## Bump major version (X.0.0)
	@echo "$(BLUE)Bumping major version...$(RESET)"
	@uv run python -c "import re; \
		v = '$(VERSION)'.split('.'); \
		v[0] = str(int(v[0]) + 1); \
		v[1] = '0'; \
		v[2] = '0'; \
		new_v = '.'.join(v); \
		content = open('openbotx/version.py').read(); \
		content = re.sub(r'__version__ = \".*\"', f'__version__ = \"{new_v}\"', content); \
		open('openbotx/version.py', 'w').write(content); \
		print(f'Version bumped to {new_v}')"
