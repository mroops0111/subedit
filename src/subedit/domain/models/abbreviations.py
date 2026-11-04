import importlib.resources


# A lone letter such as A. is an initial, which prose reading judges by whether it stands as a word of its own.
def _cldr_suppressions() -> frozenset[str]:
    data = importlib.resources.files(__name__.rpartition('.')[0]).joinpath('cldr_sentence_suppressions.txt')
    lines = data.read_text(encoding='utf-8').splitlines()
    return frozenset(line for line in lines if line and not line.startswith('#') and len(line) > 2)


# The abbreviations Unicode CLDR lists for English, each with its final period and matched with its case.
CLDR_SUPPRESSIONS = _cldr_suppressions()
# Latin abbreviations, which CLDR lists only capitalized, such as E.g., while prose mostly writes them lowercase.
_LATIN = frozenset({'al.', 'approx.', 'ca.', 'cf.', 'e.g.', 'etc.', 'i.e.', 'p.m.', 'resp.', 'viz.', 'vs.'})
# Abbreviations that point into a document, such as Fig. 3, which end no sentence only before a number.
_BEFORE_A_NUMBER = frozenset(
    {'art.', 'ch.', 'eq.', 'eqs.', 'fig.', 'figs.', 'no.', 'nos.', 'p.', 'para.', 'ref.', 'sec.', 'vol.'}
)


def ends_no_sentence(word: str, following: str, added: frozenset[str] = frozenset()) -> bool:
    """Whether a word written with its period, such as Dr., abbreviates rather than ends the sentence.

    added holds the project's own abbreviations, each written with its period and matched with its case.
    """
    if word in CLDR_SUPPRESSIONS or word in added or word.lower() in _LATIN:
        return True
    return word.lower() in _BEFORE_A_NUMBER and following.lstrip()[:1].isdigit()
