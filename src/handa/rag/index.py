"""Kitchen-binder index. Sample markdown is chunked, embedded, and stored in Chroma."""

from hashlib import sha256
import logging
import os
from pathlib import Path
import re

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")

import chromadb
from chromadb.config import Settings as ChromaSettings

logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

from handa.config import Settings
from handa.rag.embeddings import HashEmbedder

log = logging.getLogger("handa.rag")
_HEADING = re.compile(r"\n(?=# )")
SAMPLE_ROOT = Path(__file__).resolve().parent.parent / "sample_data"


def load_chunks() -> list[dict]:
    chunks: list[dict] = []
    from handa.sample_data.generate import generate_catalog

    catalog = generate_catalog()
    for recipe in catalog["recipes"]:
        bits = ", ".join(f"{item['qty']} {item['id']}" for item in recipe["ingredients"])
        chunks.append(
            {
                "id": f"recipes/{recipe['id']}",
                "text": (
                    f"{recipe['name']}. Slot {recipe['slot']}. Diet {', '.join(recipe['diet'])}. "
                    f"Proteins {', '.join(recipe['proteins']) or 'none'}. "
                    f"Per guest: {bits}. Premium: {recipe['premium']}."
                ),
                "source": f"recipes/{recipe['id']}.md",
                "title": recipe["name"],
            }
        )
    for supplier in catalog["suppliers"]:
        chunks.append(
            {
                "id": f"suppliers/{supplier['id']}",
                "text": f"{supplier['name']} lead time {supplier['lead_days']} days. Synthetic supplier.",
                "source": f"suppliers/{supplier['id']}.md",
                "title": supplier["name"],
            }
        )
    files = sorted(path for path in SAMPLE_ROOT.glob("**/*.md") if path.name != "catalog.json")
    for path in files:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        source = str(path.relative_to(SAMPLE_ROOT))
        parts = _HEADING.split(text) if text.startswith("#") else [text]
        for index, part in enumerate(parts):
            body = part.strip()
            if not body:
                continue
            title = body.splitlines()[0].lstrip("# ").strip()
            chunks.append(
                {
                    "id": f"{source}#{index}",
                    "text": body,
                    "source": source,
                    "title": title,
                }
            )
    return chunks


class KnowledgeIndex:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = Path(settings.data_dir) / "chroma"
        self.path.mkdir(parents=True, exist_ok=True)
        self.embedder = HashEmbedder()
        self.client = chromadb.PersistentClient(
            path=str(self.path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = None

    def ensure(self) -> int:
        chunks = load_chunks()
        digest = sha256("".join(chunk["id"] + chunk["text"] for chunk in chunks).encode()).hexdigest()
        marker = Path(self.settings.data_dir) / "binder.sha256"
        name = "kitchen-binder"
        existing = marker.exists() and marker.read_text(encoding="utf-8").strip() == digest
        if existing:
            try:
                self.collection = self.client.get_collection(name, embedding_function=self.embedder)
                if self.collection.count() == len(chunks):
                    log.info("kitchen binder ready chunks=%s", len(chunks))
                    return len(chunks)
            except Exception:
                log.info("rebuilding kitchen binder")
        try:
            self.client.delete_collection(name)
        except Exception:
            pass
        self.collection = self.client.create_collection(
            name,
            embedding_function=self.embedder,
            metadata={"hnsw:space": "cosine"},
        )
        self.collection.add(
            ids=[chunk["id"] for chunk in chunks],
            documents=[chunk["text"] for chunk in chunks],
            metadatas=[{"source": chunk["source"], "title": chunk["title"]} for chunk in chunks],
        )
        marker.write_text(digest, encoding="utf-8")
        log.info("indexed kitchen binder chunks=%s", len(chunks))
        return len(chunks)

    def search(self, query: str, k: int = 3) -> list[dict]:
        if self.collection is None:
            self.ensure()
        query = query.strip()
        if not query:
            return []
        found = self.collection.query(query_texts=[query], n_results=min(k, max(self.collection.count(), 1)))
        hits: list[dict] = []
        documents = (found.get("documents") or [[]])[0]
        metadatas = (found.get("metadatas") or [[]])[0]
        distances = (found.get("distances") or [[]])[0]
        for document, meta, distance in zip(documents, metadatas, distances):
            score = 1.0 - float(distance)
            excerpt = " ".join(document.split())
            if len(excerpt) > 280:
                excerpt = excerpt[:277].rstrip() + "..."
            hits.append(
                {
                    "source": meta.get("source", ""),
                    "title": meta.get("title", ""),
                    "excerpt": excerpt,
                    "score": round(score, 4),
                }
            )
        return hits

    def count(self) -> int:
        if self.collection is None:
            return 0
        return int(self.collection.count())
