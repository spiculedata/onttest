# Brackenfield register -> DuckDB. Run `make help` for the targets.
SHELL := /bin/bash
UV ?= uv
KIT_PORT ?= 8799
KIT_URL := http://127.0.0.1:$(KIT_PORT)

# FieldTrax connection: .env if present, otherwise .env.example (the kit's published demo values).
ENV_FILE := $(if $(wildcard .env),.env,.env.example)
include $(ENV_FILE)
FIELDTRAX_BASE_URL := $(KIT_URL)  # the kit on KIT_PORT (make demo KIT_PORT=8800 to use another)
export FIELDTRAX_BASE_URL FIELDTRAX_CLIENT_ID FIELDTRAX_CLIENT_SECRET

.PHONY: help install test kit run run-workbook screen internal verify all demo clean

help:
	@echo "make install       install Python $(shell cat .python-version 2>/dev/null) deps with uv"
	@echo "make test          run the tests with coverage"
	@echo "make kit           start the FieldTrax kit on port $(KIT_PORT) (foreground; leave it running)"
	@echo "make run           load the workbook and sync FieldTrax into warehouse/brackenfield.duckdb"
	@echo "make run-workbook  load the workbook only (no FieldTrax)"
	@echo "make screen        build Priya's screen (out/priya_screen.html), answers.json and out/answers_detail.json"
	@echo "make internal      build the internal DQ & MDM console and reports (out/internal/)"
	@echo "make verify        cross-check DuckDB and answers.json against the workbook, independently"
	@echo "make all           run + screen + internal + verify"
	@echo "make demo          with the kit running: fresh warehouse, reset kit, sync + label before_advance,"
	@echo "                   sync again (no change), POST /__advance, sync, build everything"
	@echo "make clean         delete the warehouse and generated outputs"

install:
	$(UV) sync

test:
	$(UV) run pytest --cov=brackenfield --cov-report=term-missing

# The kit writes brackenfield-plant-register.xlsx into its working directory, so it runs from .kit/
# to leave the project's copy untouched.
kit:
	mkdir -p .kit && cp brackenfield-kit.mjs .kit/ && cd .kit && PORT=$(KIT_PORT) node brackenfield-kit.mjs

run:
	$(UV) run brackenfield run

run-workbook:
	$(UV) run brackenfield run --skip-fieldtrax

screen:
	$(UV) run brackenfield screen

internal:
	$(UV) run brackenfield internal

verify:
	$(UV) run brackenfield verify

all: run screen internal verify

# The brief's sequence: answer as of 31 Oct from FieldTrax before /__advance, then sync the world after it.
# Starts from an empty warehouse so the "before" view holds only what the kit served before the advance.
demo:
	rm -f warehouse/brackenfield.duckdb warehouse/brackenfield.duckdb.wal
	curl -sf -X POST $(KIT_URL)/__reset > /dev/null
	mkdir -p out/sync_demo
	$(UV) run brackenfield run --label before_advance && cp out/changes.md out/sync_demo/run1_changes.md
	$(UV) run brackenfield run && cp out/changes.md out/sync_demo/run2_changes.md
	curl -sf -X POST $(KIT_URL)/__advance > /dev/null
	$(UV) run brackenfield run && cp out/changes.md out/sync_demo/run3_after_advance_changes.md
	$(UV) run brackenfield screen
	$(UV) run brackenfield internal
	$(UV) run brackenfield verify

clean:
	rm -f warehouse/brackenfield.duckdb warehouse/brackenfield.duckdb.wal
	rm -rf out/tables out/internal out/*.csv out/changes.md out/for_priya.md out/term_mapping.md .kit
