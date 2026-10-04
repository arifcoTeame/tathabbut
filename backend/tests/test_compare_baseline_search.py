from scripts import compare_baseline_search as cb


def test_exact_search_is_verbatim_only():
    corpus = cb.load_corpus()
    assert len(corpus) >= 6236 + 72
    assert cb.exact_found(corpus, "إياك نعبد وإياك نستعين")
    assert not cb.exact_found(corpus, "إياك نعبد فإياك نستعين")      # altered particle: absent, no diff available
    assert not cb.exact_found(corpus, "الصبر مفتاح الفرج")            # outside the corpus
    assert cb.exact_found(corpus, "حب الوطن من الإيمان")               # found, but exact search carries no grade


def test_every_verdict_needing_grade_or_diff_is_marked_insufficient():
    assert {"ALTERED", "NOT_AUTHENTIC", "DISPUTED", "NEEDS_REVIEW", "REFER"} <= cb.NEEDS_MORE_THAN_SEARCH
