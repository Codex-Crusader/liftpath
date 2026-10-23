# Set DATA_SCOPE=full|sample|synthetic to select the data scope.
CLI = uv run python -m liftpath.cli

.PHONY: setup data sample synthetic profile states lifts recover eval app-data plan test lint app all

setup:
	uv sync

data:
	$(CLI) data

sample:
	$(CLI) sample

synthetic:
	$(CLI) synthetic

profile:
	$(CLI) profile

states:
	$(CLI) states

lifts:
	$(CLI) lifts

recover:
	$(CLI) recover

eval:
	$(CLI) eval

plan:
	$(CLI) plan

app-data:
	$(CLI) app-data

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run python scripts/check_dashes.py

app:
	uv run streamlit run app/streamlit_app.py

all: data states lifts recover eval plan app-data
