"""Normalisation des questions : deux formulations triviales de la même question
doivent donner la même clé de cache."""

import hashlib
import re
import unicodedata


def normalize_question(question: str) -> str:
    text = unicodedata.normalize("NFKD", question)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def question_key(question: str) -> str:
    return hashlib.sha256(normalize_question(question).encode()).hexdigest()[:32]
