"""Deterministic team-name normaliser.

NFKD, accents stripped, lower-case, punctuation to spaces, whitespace collapsed (section 5.2), plus
two Stage 2 rules: the club-form tokens ``fc`` / ``afc`` are dropped (Essentials Stage 2 step 3) and
a few letters that NFKD does not decompose are transliterated. Both the stored alias and the
looked-up source spelling go through this one function, so they always agree.
"""

from __future__ import annotations

import re
import unicodedata

_TRANSLITERATE = str.maketrans(
    {"ß": "ss", "ø": "o", "æ": "ae", "œ": "oe", "ł": "l", "đ": "d", "ð": "d", "þ": "th"}
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_DROPPED_TOKENS = frozenset({"fc", "afc"})


def normalise(name: str) -> str:
    """Return the normalised spelling, or an empty string when nothing usable remains."""
    if not isinstance(name, str):
        raise TypeError("team name must be a string")
    decomposed = unicodedata.normalize("NFKD", name.lower().translate(_TRANSLITERATE))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    tokens = [t for t in _NON_ALNUM.sub(" ", stripped).split() if t]
    kept = [t for t in tokens if t not in _DROPPED_TOKENS]
    # A name made only of dropped tokens ("FC") keeps them rather than becoming empty.
    return " ".join(kept or tokens)
