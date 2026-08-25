"""Local-first, explicitly imported knowledge sources with provenance."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".xml", ".html"}


class KnowledgeStore:
    def __init__(self, db_path: Path, allowed_roots: list[Path], max_chars: int = 200_000) -> None:
        self.db_path = Path(db_path)
        self.allowed_roots = [Path(root).resolve() for root in allowed_roots]
        self.max_chars = max(1_000, min(max_chars, 1_000_000))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
                content TEXT NOT NULL, sha256 TEXT NOT NULL, imported_at TEXT NOT NULL
            )""")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _scoped(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser().resolve()
        if not candidate.is_file() or candidate.suffix.lower() not in _ALLOWED_SUFFIXES:
            raise ValueError("knowledge source must be an existing supported text file")
        if not any(candidate == root or root in candidate.parents for root in self.allowed_roots):
            raise PermissionError("knowledge source is outside configured roots")
        return candidate

    def import_source(self, raw_path: str) -> dict[str, object]:
        path = self._scoped(raw_path)
        data = path.read_bytes()
        if len(data) > self.max_chars * 4:
            raise ValueError("knowledge source is too large")
        content = data.decode("utf-8", errors="replace")[: self.max_chars]
        source_id = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:24]
        digest = hashlib.sha256(data).hexdigest()
        record = {
            "source_id": source_id,
            "path": str(path),
            "title": path.name,
            "content": content,
            "sha256": digest,
            "imported_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO sources(source_id,path,title,content,sha256,imported_at)
                VALUES(:source_id,:path,:title,:content,:sha256,:imported_at)
                ON CONFLICT(path) DO UPDATE SET title=excluded.title, content=excluded.content,
                sha256=excluded.sha256, imported_at=excluded.imported_at""",
                record,
            )
        return {key: value for key, value in record.items() if key != "content"}

    def list_sources(self, limit: int = 100) -> list[dict[str, object]]:
        limit = max(1, min(int(limit), 100))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT source_id,path,title,sha256,imported_at FROM sources "
                "ORDER BY imported_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def search(self, query: str, limit: int = 10) -> list[dict[str, object]]:
        query = re.sub(r"\s+", " ", query.strip())[:200]
        if not query:
            raise ValueError("search query is required")
        terms = [term.lower() for term in query.split() if term]
        limit = max(1, min(int(limit), 25))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT source_id,path,title,content,imported_at FROM sources"
            ).fetchall()
        results = []
        for row in rows:
            lower = row["content"].lower()
            score = sum(lower.count(term) for term in terms)
            if score:
                excerpt_at = min(
                    (lower.find(term) for term in terms if lower.find(term) >= 0), default=0
                )
                start = max(0, excerpt_at - 160)
                results.append(
                    {
                        "source_id": row["source_id"],
                        "title": row["title"],
                        "path": row["path"],
                        "score": score,
                        "excerpt": row["content"][start : start + 500],
                        "citation": f"[{row['title']}]({row['path']})",
                    }
                )
        return sorted(results, key=lambda item: (-int(item["score"]), str(item["title"])))[:limit]

    def delete(self, source_id: str) -> bool:
        with self._connect() as conn:
            result = conn.execute("DELETE FROM sources WHERE source_id = ?", (source_id,))
        return result.rowcount > 0


__all__ = ["KnowledgeStore"]
