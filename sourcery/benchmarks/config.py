# Benchmark architecture inspired by langextract (Apache 2.0) - https://github.com/google/langextract

from __future__ import annotations

from dataclasses import dataclass
import enum


class TextType(str, enum.Enum):
    ENGLISH = "english"
    JAPANESE = "japanese"
    FRENCH = "french"
    SPANISH = "spanish"


GUTENBERG_TEXTS: dict[TextType, str] = {
    TextType.ENGLISH: "https://www.gutenberg.org/files/11/11-0.txt",
    TextType.JAPANESE: "https://www.gutenberg.org/files/1982/1982-0.txt",
    TextType.FRENCH: "https://www.gutenberg.org/files/55456/55456-0.txt",
    TextType.SPANISH: "https://www.gutenberg.org/files/67248/67248-0.txt",
}


@dataclass(frozen=True)
class TokenizationConfig:
    sizes: tuple[int, ...] = (100, 1000, 10000)
    iterations: int = 10


TOKENIZATION = TokenizationConfig()
