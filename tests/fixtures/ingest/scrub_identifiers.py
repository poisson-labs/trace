"""Replace account identifiers in captured files before they are committed.

    python scrub_identifiers.py <map.json> <file or folder>...

map.json is a list of [original, replacement] pairs and is not committed, because its left side
is the identifiers. Each pair is replaced as a plain string, longest original first, wherever it
occurs in a text file (also inside a string that itself holds JSON, a URL or a traceback); no
other byte changes. A Parquet file cannot be edited as text: it is read with pyarrow, the same
pairs are replaced in every string cell and in the schema's metadata, and it is written back,
so its bytes differ from the download beyond the replaced strings. The script prints, for each
file, how many replacements each pair's right side stands for, and exits 1 if any original is
still present afterwards."""
import json
import sys
from pathlib import Path

pairs = sorted((tuple(p) for p in json.loads(Path(sys.argv[1]).read_text())), key=lambda p: -len(p[0]))
files = [f for arg in sys.argv[2:] for f in ([Path(arg)] if Path(arg).is_file() else sorted(Path(arg).rglob("*")))
         if f.is_file() and f.suffix != ".py"]


def swap(text: str, counts: dict) -> str:
    for old, new in pairs:
        if old in text:
            counts[new] = counts.get(new, 0) + text.count(old)
            text = text.replace(old, new)
    return text


def parquet(path: Path, counts: dict) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    blob = swap(json.dumps(table.to_pylist(), ensure_ascii=False, default=str), {})
    if blob == json.dumps(table.to_pylist(), ensure_ascii=False, default=str) and not any(
            old.encode() in path.read_bytes() for old, _ in pairs):
        return
    columns = []
    for name in table.column_names:
        column = table[name]
        if pa.types.is_string(column.type) or pa.types.is_large_string(column.type):
            column = pa.array([None if v is None else swap(v, counts) for v in column.to_pylist()], type=column.type)
        columns.append(column)
    meta = {swap(k.decode(), counts).encode(): swap(v.decode(), counts).encode()
            for k, v in (table.schema.metadata or {}).items()}
    pq.write_table(pa.table(columns, names=table.column_names).replace_schema_metadata(meta), path)


left = 0
for f in files:
    counts: dict = {}
    if f.suffix == ".parquet":
        parquet(f, counts)
    else:
        text = f.read_bytes().decode("utf-8")
        f.write_bytes(swap(text, counts).encode("utf-8"))
    still = [new for old, new in pairs if old.encode() in f.read_bytes()]
    left += len(still)
    if counts or still:
        print(f, counts, "STILL PRESENT: " + ", ".join(still) if still else "")
sys.exit(1 if left else 0)
