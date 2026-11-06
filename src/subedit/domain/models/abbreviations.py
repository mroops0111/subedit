import importlib.resources


# The abbreviations Unicode CLDR lists for English, each with its final period and matched with its case.
# A lone letter such as A. is an initial, which prose reading judges by whether it stands as a word of its own.
CLDR_SUPPRESSIONS = frozenset(
    line
    for line in importlib.resources.files(__name__.rpartition('.')[0])
    .joinpath('cldr_sentence_suppressions.txt')
    .read_text(encoding='utf-8')
    .splitlines()
    if line and not line.startswith('#') and len(line) > 2
)

# Latin abbreviations, which CLDR lists only capitalized, such as E.g., while prose mostly writes them lowercase.
_LATIN = frozenset({'al.', 'approx.', 'ca.', 'cf.', 'e.g.', 'etc.', 'i.e.', 'p.m.', 'resp.', 'viz.', 'vs.'})
# Abbreviations that point into a document, such as Fig. 3, which end no sentence only before a number.
_BEFORE_A_NUMBER = frozenset(
    {'art.', 'ch.', 'eq.', 'eqs.', 'fig.', 'figs.', 'no.', 'nos.', 'p.', 'para.', 'ref.', 'sec.', 'vol.'}
)


# Courtesy titles and ranks, which stand before a name, so the capitalized word after one is that name.
_TITLES = frozenset(
    {
        'capt.',
        'col.',
        'dr.',
        'gen.',
        'gov.',
        'hon.',
        'lt.',
        'maj.',
        'mr.',
        'mrs.',
        'ms.',
        'mt.',
        'mx.',
        'prof.',
        'pvt.',
        'sen.',
        'sgt.',
        'st.',
    }
)


def ends_no_sentence(word: str, following: str, added: frozenset[str] = frozenset()) -> bool:
    """Whether a word written with its period, such as Dr., abbreviates rather than ends the sentence.

    added holds the project's own abbreviations, each written with its period and matched with its case.
    Many CLDR entries, such as Go. or OK., are also words that end a sentence,
    so one ends no sentence only where its context shows an abbreviation, as Punkt reads the case of the next word.
    """
    lowered = word.lower()
    next_character = following.lstrip()[:1]
    if word in added or lowered in _LATIN or (lowered in _TITLES and word[:1].isupper()):
        return True
    if lowered in _BEFORE_A_NUMBER:
        return next_character.isdigit()
    if word in CLDR_SUPPRESSIONS:
        # A period inside the word, as in U.S. or Ph.D., marks it an abbreviation whatever follows.
        return '.' in word[:-1] or not next_character.isupper()
    return False
