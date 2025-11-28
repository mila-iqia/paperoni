import io
import re
import traceback

import pytest
from serieux import TaggedSubclass, ValidationError, deserialize, serialize


@pytest.mark.parametrize(
    "exc_type,exc_args",
    [
        (Exception, ("msg",)),
        (FileNotFoundError, ("missing-file.txt",)),
        (KeyboardInterrupt, ()),
        (ValidationError, ("bad input",)),
    ],
)
def test_ser_deser_exceptions(exc_type, exc_args):
    exc = exc_type(*exc_args)

    try:
        raise exc
    except exc_type as e:
        exc = e

    data = serialize(TaggedSubclass[BaseException], exc)
    new_exc = deserialize(TaggedSubclass[BaseException], data)

    # Capture the output of printing the traceback for exc
    buf1 = io.StringIO()
    traceback.print_exception(type(exc), exc, exc.__traceback__, file=buf1)
    tb_exc = buf1.getvalue().splitlines()

    # Capture the output of printing the traceback for new_exc
    buf2 = io.StringIO()
    traceback.print_exception(
        type(new_exc), new_exc, getattr(new_exc, "__traceback__", None), file=buf2
    )
    tb_new = buf2.getvalue().splitlines()

    # Helper: remove any lines that start with whitespace + ^, or are only made up of ~ and ^
    def strip_carets(tb_lines):
        pattern = re.compile(r"^\s*\^|^[~\^ ]+$")
        return [line for line in tb_lines if not pattern.match(line)]

    tb_exc_stripped = strip_carets(tb_exc)
    tb_new_stripped = strip_carets(tb_new)

    print("Original traceback:")
    print("=" * 80)
    print("\n".join(tb_exc_stripped))
    print("=" * 80)
    print("Deserialized traceback:")
    print("=" * 80)
    print("\n".join(tb_new_stripped))
    print("=" * 80)

    assert tb_exc_stripped == tb_new_stripped
