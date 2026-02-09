import hashlib
import json
import threading
from dataclasses import dataclass
from functools import cached_property
from typing import Any, BinaryIO, Type

import serieux
from google import genai
from google.genai import types
from paperazzi.platforms.utils import Message
from paperazzi.utils import _make_key as paperazzi_make_key, disk_cache, disk_store
from serieux.features.comment import CommentProxy, comment_field
from serieux.features.encrypt import Secret

_JSON_SCHEMA_TYPES = {
    "string": lambda x: isinstance(x, str),
    # NOTE: For now, in GenAI, enums are currently only supported for string types:
    # google.genai.errors.ClientError: 400 INVALID_ARGUMENT. {'error': {'code':
    # 400, 'message': '*
    # GenerateContentRequest.generation_config.response_schema.properties[affiliations].items.properties[category].properties[$value].enum:
    # only allowed for STRING type\n', 'status': 'INVALID_ARGUMENT'}}
    # "integer": lambda x: isinstance(x, int),
    # "number": lambda x: isinstance(x, (int, float)),
    # "boolean": lambda x: isinstance(x, bool),
    # "array": lambda x: isinstance(x, (list, tuple)),
    # "object": lambda x: isinstance(x, dict),
}

# Hack: use a thread-safe lock to avoid schema compilation conflicts in
# multi-threaded environments. Errors can look like the following:
# E ovld.utils.ResolutionError: Ambiguous resolution in <Ovld schema> for argument types [type[Analysis]]
# E Candidates are:
# E * schema[*]  (priority: (0,), specificity: [0])
# E * schema[*]  (priority: (0,), specificity: [0])
# E Note: you can use @ovld(priority=X) to give higher priority to an overload.
SERIEUX_LOCK = threading.Lock()


def cleanup_schema(schema: dict | Type[Any]) -> dict:
    """
    output_tokens: int = 0
    """
    if not isinstance(schema, dict):
        with SERIEUX_LOCK:
            schema = serieux.schema(schema).compile(ref_policy="never", root=False)

    if "enum" in schema and "type" not in schema:
        for json_type, is_type in _JSON_SCHEMA_TYPES.items():
            if all(is_type(item) for item in schema["enum"]):
                schema["type"] = json_type
                break

    for key in ["additionalProperties"]:
        if key in schema:
            del schema[key]

    for key, value in schema.items():
        if isinstance(value, dict):
            cleanup_schema(value)

    return schema


@dataclass
class PromptMetadata[T]:
    # The number of input tokens in the prompt
    input_tokens: int = None
    # The number of output tokens of the prompt
    output_tokens: int = None
    # The total number of tokens in the prompt
    total_tokens: int = None

    # The parsed output of the prompt
    parsed: T = None


@dataclass
class ParsedResponseSerializer:
    content_type: type

    def __class_getitem__(cls, content_type):
        return cls(content_type=content_type)

    def dump(self, response: types.GenerateContentResponse, file_obj: BinaryIO):
        model_dump = response.model_dump()

        if self.content_type is not None:
            metadata_type = PromptMetadata[self.content_type]
        else:
            metadata_type = PromptMetadata

        with SERIEUX_LOCK:
            model_dump = serieux.serialize(
                serieux.Comment[serieux.JSON, metadata_type],
                CommentProxy(model_dump, response._),
            )

        return file_obj.write(
            json.dumps(model_dump, indent=2, ensure_ascii=False).encode("utf-8")
        )

    def load(self, file_obj: BinaryIO) -> types.GenerateContentResponse:
        data = json.load(file_obj)

        if self.content_type is not None:
            metadata_type = PromptMetadata[self.content_type]
        else:
            metadata_type = PromptMetadata

        data = dict(data)
        comment = data.pop(comment_field, {})
        with SERIEUX_LOCK:
            response: types.GenerateContentResponse = (
                types.GenerateContentResponse.model_validate(data)
            )

            comment = serieux.deserialize(metadata_type, comment)
            response = CommentProxy(response, comment)
            response.parsed = comment.parsed

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

        return paperazzi_make_key(None, kwargs)

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
        structured_model: type = None,
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

        # Extract token information from usage_metadata
        input_tokens = response.usage_metadata.prompt_token_count
        output_tokens = (
            response.usage_metadata.candidates_token_count
            + response.usage_metadata.thoughts_token_count
        )
        total_tokens = response.usage_metadata.total_token_count

        if structured_model is not None:
            metadata_type = PromptMetadata[structured_model]
            parsed = serieux.deserialize(structured_model, response.parsed)
        else:
            metadata_type = PromptMetadata
            parsed = None

        response = CommentProxy(
            response,
            metadata_type(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                parsed=parsed,
            ),
        )

        return response


@dataclass
class PromptConfig:
    system_prompt_template: str
    extra_instructions: str = ""

    @cached_property
    def system_prompt(self):
        extra = self.extra_instructions.rstrip("\n")
        return self.system_prompt_template.replace("<EXTRA>", extra)
