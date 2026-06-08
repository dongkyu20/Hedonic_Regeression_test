# Seoul Apartment Hedonic Price Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that fetches Seoul apartment sale transactions from data.go.kr, trains a scikit-learn hedonic Ridge regression model, and predicts apartment sale prices.

**Architecture:** Keep public-data fetching, XML parsing, feature engineering, scikit-learn modeling, and CLI orchestration in focused modules under `src/hedonic_house_price`. Tests use Python `unittest`.

**Tech Stack:** Python 3.9, scikit-learn, numpy/scipy transitive dependencies, `urllib`, `xml.etree.ElementTree`, `csv`, `pickle`, `argparse`, `unittest`.

---

## File Structure

- Create `pyproject.toml`: package metadata and console script.
- Create `.gitignore`: exclude caches, artifacts, and `.env`.
- Create `.env.example`: document required API key variable without exposing secrets.
- Create `README.md`: usage and model explanation.
- Create `src/hedonic_house_price/__init__.py`: package version.
- Create `src/hedonic_house_price/law_codes.py`: Seoul district code mapping.
- Create `src/hedonic_house_price/dates.py`: recent month window generation.
- Create `src/hedonic_house_price/config.py`: `.env` loading and API-key validation.
- Create `src/hedonic_house_price/transactions.py`: dataclass and CSV IO.
- Create `src/hedonic_house_price/client.py`: API URL construction, XML parsing, and fetching.
- Create `src/hedonic_house_price/features.py`: hedonic feature transformation.
- Create `src/hedonic_house_price/linear_model.py`: scikit-learn DictVectorizer, sparse scaler, Ridge regression.
- Create `src/hedonic_house_price/modeling.py`: training, evaluation, prediction, artifact IO.
- Create `src/hedonic_house_price/cli.py`: `fetch`, `train`, `predict` commands.
- Create `tests/`: unittest suite for each behavior.

## Task 1: Project Skeleton

- [ ] Write failing import and law-code tests in `tests/test_dates_and_codes.py`.
- [ ] Run `python3 -m unittest tests.test_dates_and_codes -v` and confirm imports fail.
- [ ] Create package skeleton, `law_codes.py`, and `dates.py`.
- [ ] Re-run the test and confirm it passes.

## Task 2: XML Parsing And API Config

- [ ] Write failing tests for `.env` parsing, missing key errors, URL construction, and XML transaction parsing.
- [ ] Run `python3 -m unittest tests.test_client -v` and confirm the expected failures.
- [ ] Implement `config.py`, `transactions.py`, and `client.py`.
- [ ] Re-run the client tests and confirm they pass.

## Task 3: Hedonic Features

- [ ] Write failing tests for price normalization, log area, age, squared age, floor bands, low-floor flag, month index, and apartment-name exclusion.
- [ ] Run `python3 -m unittest tests.test_features -v` and confirm the expected failures.
- [ ] Implement `features.py`.
- [ ] Re-run the feature tests and confirm they pass.

## Task 4: scikit-learn Ridge Regression

- [ ] Write failing tests that assert the fitted estimator uses scikit-learn Pipeline, DictVectorizer, StandardScaler, and Ridge.
- [ ] Run `python3 -m unittest tests.test_linear_model -v` and confirm the expected failures.
- [ ] Implement scikit-learn feature vectorization, sparse scaling, and Ridge fitting in `linear_model.py`.
- [ ] Re-run the linear-model tests and confirm they pass.

## Task 5: Training, Evaluation, Prediction

- [ ] Write failing tests that train on synthetic apartment transactions, emit metrics, save/load an artifact, and predict KRW prices.
- [ ] Run `python3 -m unittest tests.test_modeling -v` and confirm the expected failures.
- [ ] Implement `modeling.py`.
- [ ] Re-run the modeling tests and confirm they pass.

## Task 6: CLI And Documentation

- [ ] Write failing CLI tests for `fetch --help`, `train`, and `predict` argument parsing.
- [ ] Run `python3 -m unittest tests.test_cli -v` and confirm the expected failures.
- [ ] Implement `cli.py`, `pyproject.toml`, `.gitignore`, `.env.example`, and `README.md`.
- [ ] Re-run CLI tests and the full `python3 -m unittest discover -v` suite.

## Self-Review

- Spec coverage: the plan covers public-data fetch, Seoul 24-month defaults, hedonic floor treatment, Ridge regression, model artifacts, CLI commands, and tests.
- Placeholder scan: no implementation placeholders remain in this plan.
- Type consistency: transactions flow as dataclasses to dictionaries for feature/model stages, and artifacts are JSON-compatible dictionaries.
