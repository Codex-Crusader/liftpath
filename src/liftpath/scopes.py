"""Derived data scopes (SPEC section 4)."""

from dataclasses import replace

import duckdb

from liftpath.config import Config
from liftpath.paths import canonical_dir
from liftpath.schema import CANONICAL

SAMPLE_MODULES = 2
# A module needs a train and a test presentation (SPEC section 5).
MIN_PRESENTATIONS = 2


def pick_sample_modules(con: duckdb.DuckDBPyConnection, full_dir) -> list[str]:
    """The modules with the fewest enrolled students. Ties break by module name."""
    path = (full_dir / "enrollments.parquet").as_posix()
    rows = con.execute(
        f"""SELECT module FROM read_parquet('{path}')
            GROUP BY module
            HAVING count(DISTINCT presentation) >= {MIN_PRESENTATIONS}
            ORDER BY count(*), module
            LIMIT {SAMPLE_MODULES}"""
    ).fetchall()
    return [row[0] for row in rows]


def build_sample(con: duckdb.DuckDBPyConnection, cfg: Config) -> dict:
    """Filter the full canonical tables to the sample modules."""
    full_dir = canonical_dir(replace(cfg, scope="full"))
    out_dir = canonical_dir(replace(cfg, scope="sample"))
    out_dir.mkdir(parents=True, exist_ok=True)
    modules = pick_sample_modules(con, full_dir)
    module_list = ", ".join(f"'{m}'" for m in modules)
    courses = (full_dir / "courses.parquet").as_posix()
    keep = f"course_id IN (SELECT course_id FROM read_parquet('{courses}') " \
           f"WHERE module IN ({module_list}))"
    stats = {"modules": modules}
    for table in CANONICAL:
        source = (full_dir / f"{table}.parquet").as_posix()
        target = (out_dir / f"{table}.parquet").as_posix()
        con.execute(
            f"COPY (SELECT * FROM read_parquet('{source}') WHERE {keep}) TO '{target}' "
            f"(FORMAT parquet)"
        )
        stats[table] = con.execute(f"SELECT count(*) FROM read_parquet('{target}')").fetchone()[0]
    return stats
