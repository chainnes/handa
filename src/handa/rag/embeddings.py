"""Local embeddings. Hashing vectors need no download and no API key.

They are real vectors: same words land in the same dimensions, and Chroma ranks
chunks by cosine similarity. They are not a neural model. A neural embedder can
replace `embed()` without changing the index.
"""

import hashlib
import math
import re

DIM = 384
_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    words = _TOKEN.findall(text.lower())
    bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:])]
    return words + bigrams


def embed(text: str) -> list[float]:
    vector = [0.0] * DIM
    for token in tokens(text):
        digest = hashlib.blake2b(token.encode(), digest_size=16).digest()
        for slot in range(4):
            number = int.from_bytes(digest[slot * 4 : (slot + 1) * 4], "little")
            index = number % DIM
            sign = 1.0 if (number >> 8) & 1 else -1.0
            vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


class HashEmbedder:
    """Chroma calls this with a list of documents and expects a list of vectors."""

    def __call__(self, input):  # noqa: A002 — Chroma's embedding protocol uses this name
        return [embed(text) for text in input]

    def name(self) -> str:
        return "handa-hash-v1"
