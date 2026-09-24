"""The two traps from the episode's opening, measured for real.

    uv run python harness/traps.py go        `go test` on a package with no tests
    uv run python harness/traps.py postgres  writes during CREATE INDEX, with and without CONCURRENTLY

The Postgres run starts a throwaway postgres:16-alpine container on port 55432
and removes it afterwards.
"""

import datetime
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import time

OUT = pathlib.Path(__file__).resolve().parents[1] / "results" / "harness"


def save(name, payload):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(payload, indent=1))
    print(f"  wrote {name}.json")


# ---- go test with no test files ----------------------------------------------------------------
GO = {
    "go.mod": "module example.com/billing\n\ngo 1.25\n",
    "internal/invoice/discount.go": "package invoice\n\nfunc Discount(subtotal, pct int64) int64 { return subtotal * pct / 100 }\n",
    "internal/invoice/discount_test.go": 'package invoice\n\nimport "testing"\n\nfunc TestDiscount(t *testing.T) {\n\tif got := Discount(100000, 10); got != 9000 {\n\t\tt.Fatalf("Discount = %d, want 9000", got)\n\t}\n}\n',
    "internal/api/handler.go": 'package api\n\nfunc Handler() string { return "ok" }\n',
}


def go_trap():
    d = pathlib.Path(tempfile.mkdtemp(prefix="gotrap-"))
    for f, s in GO.items():
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        (d / f).write_text(s)
    runs = []
    for cmd in (["go", "test", "./internal/api"], ["go", "test", "./..."]):
        r = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
        out = (r.stdout + r.stderr).replace(str(d), ".").strip()
        runs.append({"cmd": " ".join(cmd), "exit": r.returncode, "output": out})
        print(f"  {' '.join(cmd)} -> exit {r.returncode}")
    go_version = subprocess.run(
        ["go", "version"], capture_output=True, text=True
    ).stdout.strip()
    save(
        "go_trap",
        {
            "go": go_version,
            "files": GO,
            "runs": runs,
            "run_at": datetime.datetime.now().isoformat(timespec="seconds"),
        },
    )


# ---- CREATE INDEX vs writes ---------------------------------------------------------------------
PORT, NAME, ROWS = 55432, "harness-geek-pg", 30_000_000


def pg_trap():
    import psycopg

    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            NAME,
            "-e",
            "POSTGRES_PASSWORD=pw",
            "-p",
            f"{PORT}:5432",
            "postgres:16-alpine",
            "-c",
            "maintenance_work_mem=64MB",
            "-c",
            "max_parallel_maintenance_workers=0",
        ],
        check=True,
        capture_output=True,
    )
    dsn = f"postgresql://postgres:pw@localhost:{PORT}/postgres"
    try:
        for _ in range(60):
            try:
                psycopg.connect(dsn, connect_timeout=2).close()
                break
            except psycopg.OperationalError:
                time.sleep(1)
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(
                "create table invoices (id bigserial primary key, customer_id bigint, total_paise bigint, created timestamptz default now())"
            )
            t0 = time.time()
            c.execute(
                f"insert into invoices (customer_id, total_paise) select (random()*1e6)::bigint, (random()*1e7)::bigint from generate_series(1, {ROWS})"
            )
            c.execute("vacuum analyze invoices")
            print(f"  loaded {ROWS:,} rows in {time.time() - t0:.1f} s")
            version = c.execute("show server_version").fetchone()[0]
        results = {}
        for mode in ("plain", "concurrently"):
            with psycopg.connect(dsn, autocommit=True) as c:
                c.execute("drop index if exists invoices_customer_idx")
            samples, stop = [], threading.Event()

            def writer():
                with psycopg.connect(dsn, autocommit=True) as w:
                    while not stop.is_set():
                        s = time.time()
                        w.execute(
                            "insert into invoices (customer_id, total_paise) values (42, 100)"
                        )
                        samples.append((s, time.time() - s))
                        time.sleep(0.05)

            th = threading.Thread(target=writer)
            th.start()
            time.sleep(2.0)
            with psycopg.connect(dsn, autocommit=True) as c:
                i0 = time.time()
                c.execute(
                    f"create index {'concurrently ' if mode == 'concurrently' else ''}invoices_customer_idx on invoices (customer_id)"
                )
                i1 = time.time()
            time.sleep(2.0)
            stop.set()
            th.join()
            base = samples[0][0]
            lat = [d for _, d in samples]
            results[mode] = {
                "index_start": round(i0 - base, 3),
                "index_end": round(i1 - base, 3),
                "index_seconds": round(i1 - i0, 2),
                "inserts": len(samples),
                "max_insert_seconds": round(max(lat), 3),
                "inserts_over_1s": sum(d > 1 for d in lat),
                "samples": [[round(s - base, 3), round(d, 4)] for s, d in samples],
            }
            print(
                f"  {mode:<12} index {i1 - i0:5.1f} s; {len(samples)} inserts; slowest {max(lat):.2f} s"
            )
        save(
            "pg_trap",
            {
                "postgres": version,
                "rows": ROWS,
                "run_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "insert_every_s": 0.05,
                "results": results,
            },
        )
    finally:
        subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)


if __name__ == "__main__":
    which = sys.argv[1:] or ["go", "postgres"]
    if "go" in which:
        go_trap()
    if "postgres" in which:
        pg_trap()
