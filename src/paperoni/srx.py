from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any

from ovld import Medley, ovld, recurse
from serieux import JSON
from serieux.ctx import Context
from serieux.priority import STD


@dataclass
class MockCode:
    co_filename: str
    co_name: str
    co_firstlineno: int = 0
    co_argcount: int = 0
    co_flags: int = 0
    co_varnames: tuple[str, ...] = ()
    co_consts: tuple[Any, ...] = ()
    co_names: tuple[str, ...] = ()
    co_freevars: tuple[str, ...] = ()
    co_cellvars: tuple[str, ...] = ()


@dataclass
class MockFrame:
    f_back: MockFrame | None
    f_code: MockCode
    f_globals: dict[str, Any]
    f_locals: dict[str, Any]
    f_lineno: int
    f_lasti: int = -1
    f_trace: Any = None


@dataclass
class MockTraceback:
    tb_next: MockTraceback | None
    tb_frame: MockFrame
    tb_lineno: int
    tb_lasti: int = -1


class FakeException(BaseException):
    def __init__(self, *args, **kwargs):
        self._tb = None
        super().__init__(*args, **kwargs)

    @property
    def __traceback__(self):
        return self._tb

    @__traceback__.setter
    def __traceback__(self, value):
        self._tb = value

    def with_traceback(self, value):
        self._tb = value
        return self


class ExceptionSerialization(Medley):
    """Feature for serializing and deserializing exceptions with tracebacks."""

    @ovld(priority=STD)
    def serialize(self, t: type[BaseException], obj: BaseException, ctx: Context, /):
        """Serialize an exception to a dictionary including its traceback as structured locations."""
        match obj.args:
            case (str(s),):
                result = {"message": s}
            case _:
                args = []
                for arg in obj.args:
                    try:
                        value = recurse(JSON, arg)
                    except Exception:
                        value = f"<could not serialize {arg}>"
                    args.append(value)
                result = {"args": args}

        # Include traceback as list of TracebackFrame objects if available
        if obj.__traceback__ is not None:
            tb_list = []
            tb = obj.__traceback__
            while tb is not None:
                frame = tb.tb_frame
                line = None
                extracted = traceback.extract_tb(tb, limit=1)
                if extracted:
                    line = extracted[0].line

                data = {
                    "name": frame.f_code.co_name,
                    "line": line,
                    "filename": frame.f_code.co_filename,
                    "lineno": tb.tb_lineno,
                }
                tb_list.append(data)
                tb = tb.tb_next

            result["traceback"] = tb_list

        return result

    @ovld(priority=STD)
    def deserialize(self, t: type[BaseException], obj: dict, ctx: Context, /):
        """Deserialize an exception from a dictionary.

        Supports 'message' as shorthand for args: [message].
        """
        if not isinstance(obj, dict):
            raise ValueError(
                f"Expected dict for exception deserialization, got {type(obj)}"
            )

        # Handle 'message' shorthand
        if "message" in obj and "args" not in obj:
            args = [obj["message"]]
        else:
            args = obj.get("args", [])

        # Create the exception instance
        old_t = t
        t = type(t.__name__, (t, FakeException), {})
        t.__module__ = old_t.__module__
        try:
            exc = t(*args)
        except Exception:
            # If we can't instantiate with args, try without
            exc = t()

        # Deserialize traceback frames if present
        # (We store them but can't reconstruct actual traceback objects)
        if "traceback" in obj:
            # Instantiate a mock (reconstructed) traceback structure using TracebackInfo and FrameInfo.
            # This does NOT recreate real traceback objects, but provides a structured form.
            previous_tb = None
            for frame_data in reversed(obj["traceback"]):
                frame_info = MockFrame(
                    f_back=None,
                    f_code=MockCode(
                        co_filename=frame_data.get("filename", "???"),
                        co_name=frame_data.get("name", "???"),
                    ),
                    f_globals={},
                    f_locals={},
                    f_lineno=frame_data.get("lineno", 0),
                    f_lasti=-1,
                    f_trace=None,
                )
                tb_info = MockTraceback(
                    tb_next=previous_tb,
                    tb_frame=frame_info,
                    tb_lasti=-1,
                    tb_lineno=frame_data.get("lineno", 0),
                )
                previous_tb = tb_info
            exc.__traceback__ = previous_tb
            # # Deserialize each frame for potential display/logging
            # frames = [recurse(TracebackFrame, frame_data, ctx) for frame_data in obj["traceback"]]
            # # Store the frames as an attribute for later access if needed
            # exc.__serieux_traceback__ = frames

        return exc

    @ovld(priority=STD)
    def schema(self, t: type[BaseException], ctx: Context, /):
        """Generate JSON schema for exception serialization."""
        return {
            "type": "object",
            "properties": {
                "args": {
                    "type": "array",
                    "description": "Exception arguments",
                },
                "message": {
                    "type": "string",
                    "description": "Shorthand for args with a single message string",
                },
                "traceback": {
                    "type": "array",
                    "description": "List of traceback frames",
                    "items": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "lineno": {"type": "integer"},
                            "name": {"type": "string"},
                            "line": {"type": "string"},
                        },
                        "required": ["filename", "lineno", "name"],
                    },
                },
            },
            "oneOf": [
                {"required": ["args"]},
                {"required": ["message"]},
            ],
        }
