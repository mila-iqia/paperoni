from unittest.mock import MagicMock, patch

import pytest

from paperoni.model import Link
from paperoni.utils import asciiify, expand_links_dict, mostly_latin, soft_fail


@pytest.mark.parametrize(
    "links,expected",
    [
        (
            [
                Link(type="arxiv", link="1234.5678"),
                Link(type="doi", link="10.1000/xyz"),
                Link(type="unknown", link="foo"),
            ],
            [
                {
                    "type": "doi.abstract",
                    "link": "10.1000/xyz",
                    "url": "https://doi.org/10.1000/xyz",
                },
                {
                    "type": "arxiv.abstract",
                    "link": "1234.5678",
                    "url": "https://arxiv.org/abs/1234.5678",
                },
                {
                    "type": "arxiv.pdf",
                    "link": "1234.5678",
                    "url": "https://arxiv.org/pdf/1234.5678.pdf",
                },
                {"type": "unknown", "link": "foo"},
            ],
        ),
        (
            [
                Link(type="openreview", link="abc123"),
            ],
            [
                {
                    "type": "openreview.abstract",
                    "link": "abc123",
                    "url": "https://openreview.net/forum?id=abc123",
                },
                {
                    "type": "openreview.pdf",
                    "link": "abc123",
                    "url": "https://openreview.net/pdf?id=abc123",
                },
            ],
        ),
        (
            [
                Link(type="mlr", link="42/quack"),
            ],
            [
                {
                    "type": "mlr.abstract",
                    "link": "42/quack",
                    "url": "https://proceedings.mlr.press/v42/quack.html",
                },
                {
                    "type": "mlr.pdf",
                    "link": "42/quack",
                    "url": "https://proceedings.mlr.press/v42/quack/quack.pdf",
                },
            ],
        ),
        (
            [
                Link(type="dblp", link="dblpkey"),
            ],
            [
                {
                    "type": "dblp.abstract",
                    "link": "dblpkey",
                    "url": "https://dblp.uni-trier.de/rec/dblpkey",
                },
            ],
        ),
        (
            [
                Link(type="semantic_scholar", link="semid"),
            ],
            [
                {
                    "type": "semantic_scholar.abstract",
                    "link": "semid",
                    "url": "https://www.semanticscholar.org/paper/semid",
                },
            ],
        ),
        (
            [
                Link(type="orcid", link="0000-0002-1825-0097"),
            ],
            [
                {
                    "type": "orcid.abstract",
                    "link": "0000-0002-1825-0097",
                    "url": "https://orcid.org/0000-0002-1825-0097",
                },
            ],
        ),
        (
            [
                Link(type="unknown_type", link="bar"),
            ],
            [
                {"type": "unknown_type", "link": "bar"},
            ],
        ),
    ],
)
def test_expand_links_dict_types_and_fields(links, expected):
    result = expand_links_dict(links)
    # Only compare the fields present in expected (ignore extra fields in result)
    for res, exp in zip(result, expected):
        for k, v in exp.items():
            assert res[k] == v
    assert [d["type"] for d in result] == [d["type"] for d in expected]


@pytest.mark.parametrize(
    "input_str,expected",
    [
        ("café", "cafe"),
        ("über", "uber"),
        ("façade", "facade"),
        ("résumé", "resume"),
        ("crème brûlée", "creme brulee"),
        ("", ""),
        ("ASCII only", "ASCII only"),
        ("你好", ""),  # Non-Latin, should be removed
        ("Γειά σου", " "),  # Greek with a space
        ("東京", ""),  # Japanese, should be removed
    ],
)
def test_asciiify(input_str, expected):
    assert asciiify(input_str) == expected


@pytest.mark.parametrize(
    "input_str,expected",
    [
        ("バイオディーゼル燃料【Powered by NICT】", False),
        ("café", True),  # accented Latin
        ("crème brûlée", True),  # accented Latin with space
        ("", True),  # empty string
        ("ASCII only", True),  # all ASCII
        ("你好", False),  # Chinese, not Latin
        ("Γειά σου", False),  # Greek, not Latin
        ("café 東京", False),  # mixed, not threshold
        ("café café café café 東京", True),  # 50% Latin, default threshold 0.9
    ],
)
def test_mostly_latin_default(input_str, expected):
    assert mostly_latin(input_str) == expected


@pytest.mark.parametrize(
    "input_str,threshold,expected",
    [
        ("A東", 0.4, True),
        ("A東", 0.5, True),
        ("A東", 0.6, False),
    ],
)
def test_mostly_latin_threshold(input_str, threshold, expected):
    assert mostly_latin(input_str, threshold=threshold) == expected


def test_soft_fail_no_exception():
    """Test that soft_fail works normally when no exception is raised."""
    with soft_fail("test message"):
        result = 42
    assert result == 42


@pytest.mark.parametrize("message", [None, "Custom test message"])
def test_soft_fail_suppresses_exception(message: str | None):
    """Test that soft_fail suppresses regular exceptions."""
    err = ValueError("test error")
    if message is None:
        log_message = repr(err)
    else:
        log_message = message

    mock_logger = MagicMock()
    with (
        patch("paperoni.utils.logging.getLogger", return_value=mock_logger),
        patch("paperoni.utils.send") as mock_send,
    ):
        with soft_fail(message):
            raise err

        # Exception should be logged
        mock_logger.exception.assert_called_once()
        assert log_message in [
            *mock_logger.exception.call_args.args,
            *mock_logger.exception.call_args.kwargs.values(),
        ]

        # Exception should be sent
        mock_send.assert_called_once()
        assert mock_send.call_args.kwargs["exception"] is err


@pytest.mark.parametrize("exception", [KeyboardInterrupt, GeneratorExit, SystemExit])
def test_soft_fail_exception_propagates(exception: type[BaseException]):
    """Test that KeyboardInterrupt, GeneratorExit, and SystemExit are not
    suppressed and propagate."""
    with pytest.raises(exception):
        with soft_fail():
            raise exception()


def test_generator_exit_propagates():
    """Test that GeneratorExit is not suppressed and propagates."""

    def gen_func():
        with pytest.raises(GeneratorExit):
            with soft_fail():
                yield 1

    gen = gen_func()
    next(gen)
    gen.close()
