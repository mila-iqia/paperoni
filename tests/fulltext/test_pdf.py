import pytest

from paperoni.fulltext.pdf import CachePolicies, get_pdf


def test_get_pdf(file_regression):
    ref = "openreview:vieIamY2Gi"

    with pytest.raises(Exception, match="No fulltext found for any reference"):
        get_pdf(ref, CachePolicies.NO_DOWNLOAD)

    p = get_pdf(ref)
    file_regression.check(p.meta_path.read_text())


def test_get_best_pdf():
    ref1 = "openreview:G7X1hsBLNl"
    ref2 = "arxiv:2506.10137"
    refs = [ref1, ref2]

    # Fetch the second ref so that it's already downloaded
    p2 = get_pdf(ref2)

    p_use = get_pdf(refs, CachePolicies.USE)
    assert p_use == p2

    p_no_d = get_pdf(refs, CachePolicies.NO_DOWNLOAD)
    assert p_no_d == p2

    # This will download the first one
    p_best = get_pdf(refs, CachePolicies.USE_BEST)
    assert p_best != p2

    p_use = get_pdf(refs, CachePolicies.USE)
    assert p_use == p_best
