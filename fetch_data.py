"""Download the one dataset this repository does not redistribute.

The Geometry of Truth cities set (Marks and Tegmark, 2023) has no licence file upstream,
so it is fetched from its source, pinned to the commit the results were measured on.

    uv run python fetch_data.py
"""

import hashlib
import pathlib
import urllib.request

URL = "https://raw.githubusercontent.com/saprmarks/geometry-of-truth/5d1c630c44f7e50bda7ad86d601ccadf9abc5ddb/datasets/cities.csv"
DEST = pathlib.Path(__file__).resolve().parent / "corpus" / "cities.csv"

if __name__ == "__main__":
    data = urllib.request.urlopen(URL, timeout=60).read()
    rows = data.decode().count("\n") - 1
    if rows < 100:
        raise SystemExit(f"only {rows} rows downloaded")
    DEST.write_bytes(data)
    print(f"  wrote {DEST.name}: {rows} rows, sha256 {hashlib.sha256(data).hexdigest()[:16]}")
