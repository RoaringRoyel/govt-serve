"""A small, dependency-free Retrieval-Augmented Generation pipeline.

    question --> Retriever (TF-IDF over knowledge chunks + the citizen's own requests)
             --> AnswerGenerator (extractive by default; swap in an LLM without touching the rest)

Every piece is behind a tiny interface so it can be replaced independently.
"""
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
USER_SOURCE = "Your requests"
FALLBACK = (
    "I couldn't find that in our guides. Please add a remark to your request or contact the service office "
    "and an officer will help you."
)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "have", "how", "i", "if",
    "in", "is", "it", "me", "my", "of", "on", "or", "should", "the", "to", "was", "what", "when", "where", "which",
    "who", "will", "with", "you", "your", "need", "get", "there", "this", "that",
}
TOKEN_RE = re.compile(r"[a-z0-9]+")


def _stem(token):
    if len(token) > 5 and token.endswith("ly"):  # currently -> current
        token = token[:-2]
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("uses"):  # statuses -> status
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us")):
        return token[:-1]
    return token


def tokenize(text):
    return [_stem(t) for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


@dataclass(frozen=True)
class Chunk:
    source: str
    heading: str
    text: str


# ---------------- knowledge base ----------------
def parse_markdown(name, text):
    title, heading, buf, chunks = name.replace("_", " ").title(), "Overview", [], []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            chunks.append(Chunk(title, heading, body))

    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            flush()
            heading, buf[:] = line[3:].strip(), []
        else:
            buf.append(line)
    flush()
    return chunks


@lru_cache(maxsize=1)
def load_knowledge_chunks():
    chunks = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        chunks.extend(parse_markdown(path.stem, path.read_text(encoding="utf-8")))
    return tuple(chunks)


def citizen_request_chunks(user, limit=10):
    """The asking citizen's own requests, so 'what is the status of my passport request?' works."""
    from apps.service_requests.models import ServiceRequest

    chunks = []
    qs = ServiceRequest.objects.filter(citizen=user).select_related("category", "officer")[:limit]
    for r in qs:
        officer = f" Assigned officer: {r.officer.full_name}." if r.officer_id else " No officer assigned yet."
        chunks.append(
            Chunk(
                USER_SOURCE,
                f"Request #{r.pk}",
                f"Your request #{r.pk} '{r.title}' ({r.category.name}, {r.get_priority_display()} priority). "
                f"Current status: {r.get_status_display()}.{officer}",
            )
        )
    return chunks


# ---------------- retrieval ----------------
class Retriever(ABC):
    @abstractmethod
    def search(self, query, k=3): ...


class TfidfRetriever(Retriever):
    def __init__(self, chunks):
        self.chunks = list(chunks)
        docs = [tokenize(f"{c.source} {c.heading} {c.text}") for c in self.chunks]
        df = Counter()
        for tokens in docs:
            df.update(set(tokens))
        n = len(docs)
        self.idf = {t: math.log((1 + n) / (1 + d)) + 1 for t, d in df.items()}
        self.vectors = [self._vector(tokens) for tokens in docs]

    def _vector(self, tokens):
        vec = {t: (1 + math.log(c)) * self.idf[t] for t, c in Counter(tokens).items() if t in self.idf}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def search(self, query, k=3):
        q = self._vector(tokenize(query))
        scored = [(c, sum(w * v.get(t, 0.0) for t, w in q.items())) for c, v in zip(self.chunks, self.vectors)]
        return sorted([s for s in scored if s[1] > 0], key=lambda s: s[1], reverse=True)[:k]


# ---------------- generation ----------------
class AnswerGenerator(ABC):
    @abstractmethod
    def generate(self, question, hits): ...


class ExtractiveAnswerGenerator(AnswerGenerator):
    """Builds the answer from the best retrieved passages - no external model, no hallucinations."""

    def __init__(self, max_passages=2):
        self.max_passages = max_passages

    def generate(self, question, hits):
        if not hits:
            return FALLBACK
        parts = [f"{chunk.source} - {chunk.heading}:\n{chunk.text}" for chunk, _ in hits[: self.max_passages]]
        return "\n\n".join(parts)


# ---------------- orchestration ----------------
class RAGService:
    PERSONAL_HINT = re.compile(r"\b(my|status|current|update|progress|track|where)\b", re.I)

    def __init__(self, generator=None, knowledge_loader=load_knowledge_chunks, user_context=citizen_request_chunks,
                 retriever_factory=TfidfRetriever, min_score=0.12):
        self.generator = generator or ExtractiveAnswerGenerator()
        self.knowledge_loader = knowledge_loader
        self.user_context = user_context
        self.retriever_factory = retriever_factory
        self.min_score = min_score

    def answer(self, question, user=None):
        chunks = list(self.knowledge_loader())
        user_chunks = list(self.user_context(user)) if user is not None else []
        chunks += user_chunks
        hits = self.retriever_factory(chunks).search(question, k=6)
        if self.PERSONAL_HINT.search(question):  # "what is my current status" -> use the user's own data
            hits = [(c, s * 1.5 if c.source == USER_SOURCE else s) for c, s in hits]
            found = {c for c, _ in hits}
            # personal questions always get the user's requests, even when no words overlap
            hits += [(c, self.min_score * 2) for c in user_chunks if c not in found]
            hits.sort(key=lambda h: h[1], reverse=True)
        hits = [(c, s) for c, s in hits if s >= self.min_score][:3]
        return {
            "answer": self.generator.generate(question, hits),
            "sources": [{"source": c.source, "heading": c.heading, "score": round(s, 3)} for c, s in hits],
        }