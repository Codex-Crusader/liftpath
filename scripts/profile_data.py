"""Write reports/data_profile_<scope>.md for the canonical tables of one scope."""

import sys

from liftpath.config import load_config
from liftpath.db import connect
from liftpath.paths import REPORTS_DIR, canonical_dir
from liftpath.schema import CANONICAL


def md_table(header: list[str], rows: list[tuple]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def main() -> int:
    cfg = load_config()
    con = connect(cfg)
    folder = canonical_dir(cfg)
    for table in CANONICAL:
        path = (folder / f"{table}.parquet").as_posix()
        con.execute(f"CREATE TEMP VIEW {table} AS SELECT * FROM read_parquet('{path}')")

    counts = [(t, f"{con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:,}") for t in CANONICAL]

    null_rows = []
    for table, columns in CANONICAL.items():
        exprs = ", ".join(f"1 - count({c}) / count(*)" for c in columns)
        shares = con.execute(f"SELECT {exprs} FROM {table}").fetchone()
        null_rows += [(table, c, f"{s:.3f}") for c, s in zip(columns, shares, strict=True)]

    presentations = con.execute(
        "SELECT module, count(*), string_agg(presentation, ', ' ORDER BY presentation) "
        "FROM courses GROUP BY module ORDER BY module"
    ).fetchall()
    students = con.execute(
        "SELECT course_id, count(*) FROM enrollments GROUP BY course_id ORDER BY course_id"
    ).fetchall()
    click_share = con.execute(
        """SELECT i.item_type, sum(e.clicks) AS clicks,
                  round(sum(e.clicks) / sum(sum(e.clicks)) OVER (), 4) AS share
           FROM events e JOIN items i USING (course_id, item_id)
           GROUP BY i.item_type ORDER BY clicks DESC"""
    ).fetchall()

    sections = [
        f"# Data profile: {cfg.scope}",
        "## Row counts\n\n" + md_table(["table", "rows"], counts),
        "## Null share per column\n\n" + md_table(["table", "column", "null share"], null_rows),
        "## Presentations per module\n\n"
        + md_table(["module", "presentations", "codes"], presentations),
        "## Students per course_id\n\n" + md_table(["course_id", "students"], students),
        "## Click share per item type\n\n"
        + md_table(["item_type", "clicks", "share"], [(t, f"{c:,}", s) for t, c, s in click_share]),
    ]
    REPORTS_DIR.mkdir(exist_ok=True)
    report = REPORTS_DIR / f"data_profile_{cfg.scope}.md"
    report.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    print(report.as_posix())
    print(md_table(["table", "rows"], counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
