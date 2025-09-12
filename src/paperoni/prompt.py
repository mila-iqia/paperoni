import hashlib
import json
from dataclasses import dataclass
from typing import Any, BinaryIO, Type

import serieux
from google import genai
from google.genai import types
from paperazzi.platforms.utils import Message
from paperazzi.utils import _make_key, disk_cache, disk_store
from serieux.features.encrypt import Secret


def cleanup_schema(schema: dict | Type[Any]) -> dict:
    """
    Recursively clean up the schema removing $schema and unsupported additionalProperties
    """
    if not isinstance(schema, dict):
        # $schema is removed by root=False
        schema = serieux.schema(schema).compile(ref_policy="never", root=False)

    for key in ["additionalProperties"]:
        if key in schema:
            del schema[key]

    for key, value in schema.items():
        if isinstance(value, dict):
            cleanup_schema(value)

    return schema


@dataclass
class ParsedResponseSerializer:
    content_type: Any

    def __class_getitem__(cls, content_type):
        return cls(content_type=content_type)

    def dump(self, response: types.GenerateContentResponse, file_obj: BinaryIO):
        model_dump = response.model_dump()
        if self.content_type is not None:
            model_dump["parsed"] = serieux.serialize(self.content_type, response.parsed)
        return file_obj.write(
            json.dumps(model_dump, indent=2, ensure_ascii=False).encode("utf-8")
        )

    def load(self, file_obj: BinaryIO) -> types.GenerateContentResponse:
        data = json.load(file_obj)
        response = types.GenerateContentResponse.model_validate(data)
        if self.content_type is not None:
            response.parsed = serieux.deserialize(self.content_type, data["parsed"])
        return response


@dataclass
class Prompt:
    model: str
    client: Any = None

    @disk_store
    @disk_cache
    @staticmethod
    def prompt(
        client: genai.Client,
        *,
        messages: list[Message],
        model: str,
        structured_model: Type[Any] = None,
    ):
        raise NotImplementedError

    @staticmethod
    def _make_key(_: tuple, kwargs: dict) -> str:
        raise NotImplementedError


@dataclass
class GenAIPrompt(Prompt):
    client: genai.Client = None
    api_key: Secret[str] = None

    def __post_init__(self):
        if self.client is None:
            self.client = genai.Client(api_key=self.api_key or None)

    @disk_store
    @disk_cache(
        serializer=ParsedResponseSerializer(content_type=None),
        make_key=_make_key,
    )
    @staticmethod
    def prompt(
        client: genai.Client,
        *,
        messages: list[Message],
        model: str,
        structured_model: Type[Any] = None,
    ) -> types.GenerateContentResponse:
        """Generate a prompt for a list of messages.

        Args:
            client: VertexAI client
            messages: List of messages
            model: Model to use
            structured_model: Structured model to use
        """
        # Generate the response
        contents = []
        for message in [m.format_message() for m in messages]:
            if message["role"] == "application/pdf":
                contents.append(
                    types.Part.from_bytes(
                        data=message["content"].read_bytes(),
                        mime_type=message["role"],
                    )
                )
            else:
                contents.append(message["content"])

        config = None
        if structured_model:
            # Avoid INVALID_ARGUMENT error from sending the serieux.schema.compile()
            # using response_json_schema by parsing the schema into a genai.types.Schema
            # {
            #     "response_mime_type": "application/json",
            #     "response_json_schema": serieux.schema(structured_model).compile(ref_policy="never"),
            # }
            # google.genai.errors.ClientError: 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'A schema in GenerationConfig in the request exceeds the maximum allowed nesting depth.', 'status': 'INVALID_ARGUMENT'}}
            schema = types.Schema.model_validate(cleanup_schema(structured_model))
            config = {
                "response_mime_type": "application/json",
                "response_schema": schema,
            }

        response = client.models.generate_content(
            contents=contents, model=model, config=config
        )

        if structured_model:
            response.parsed = serieux.deserialize(structured_model, response.parsed)

        return response

    @staticmethod
    def _make_key(_: tuple, kwargs: dict) -> str:
        kwargs = kwargs.copy()
        kwargs.pop("client", None)
        kwargs["messages"] = kwargs["messages"][:]
        for i, message in enumerate(kwargs["messages"]):
            message: Message
            if message.type == "application/pdf":
                kwargs["messages"][i] = Message(
                    type=message.type,
                    prompt=hashlib.sha256(message.content.read_bytes()).hexdigest(),
                    args=message.args,
                    kwargs=message.kwargs,
                )
        kwargs["structured_model"] = cleanup_schema(kwargs.pop("structured_model", None))

        return _make_key(None, kwargs)
