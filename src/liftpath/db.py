"""DuckDB connection with the memory and thread limits from config.yaml."""

import duckdb

from liftpath.config import Config
from liftpath.paths import TMP_DIR


def connect(cfg: Config) -> duckdb.DuckDBPyConnection:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{cfg.duckdb_memory_limit}'")
    con.execute(f"SET threads = {cfg.duckdb_threads}")
    con.execute(f"SET temp_directory = '{TMP_DIR.as_posix()}'")
    return con
