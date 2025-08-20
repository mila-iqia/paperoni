import json
from dataclasses import dataclass
from typing import BinaryIO

import serieux
from google import genai
from google.genai import types
from paperazzi.platforms.utils import Message
from paperazzi.utils import DiskStore, _make_key, disk_cache, disk_store

from paperoni.config import config
from paperoni.fulltext.pdf import CachePolicies, get_pdf
from paperoni.model.classes import (
    Author,
    Institution,
    Link,
    Paper,
    PaperAuthor,
    PaperInfo,
)
from paperoni.refinement.pdf.model import SYSTEM_MESSAGE, Analysis


def cleanup_schema(schema: dict) -> dict:
    # recusively clean up the schema removing $schema and unsupported additionalProperties
    for key in ["$schema", "additionalProperties"]:
        if key in schema:
            del schema[key]

    for key, value in schema.items():
        if isinstance(value, dict):
            cleanup_schema(value)

    return schema


@dataclass
class ParsedResponseSerializer:
    content_type: Analysis

    def __class_getitem__(cls, content_type):
        return cls(content_type=content_type)

    def dump(self, response: types.GenerateContentResponse, file_obj: BinaryIO):
        model_dump = response.model_dump()
        return file_obj.write(
            json.dumps(model_dump, indent=2, ensure_ascii=False).encode("utf-8")
        )

    def load(self, file_obj: BinaryIO) -> types.GenerateContentResponse:
        data = json.load(file_obj)
        response = types.GenerateContentResponse.model_validate(data)
        response.parsed = serieux.deserialize(self.content_type, data["parsed"])
        return response


@disk_store(
    store=DiskStore(
        cache_dir=config.data_path / "pdf",
        make_key=lambda _, kwargs: _make_key(
            None, {k: v for k, v in kwargs.items() if k not in ("client",)}
        ),
        index=0,
    )
)
@disk_cache(serializer=ParsedResponseSerializer[Analysis])
def prompt(
    client: genai.Client,
    messages: list[Message],
    model: str,
    structured_model: Analysis = None,
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
        schema = types.Schema.model_validate(
            cleanup_schema(serieux.schema(structured_model).compile(ref_policy="never"))
        )
        config = {
            "response_mime_type": "application/json",
            "response_schema": schema,
        }

    return client.models.generate_content(contents=contents, model=model, config=config)


def analyse_pdf(type: str, link: str) -> PaperInfo:
    key = f"{type}:{link}"
    p = get_pdf(key, cache_policy=CachePolicies.USE_BEST)

    if p is None:
        return None

    client = genai.Client()
    model = config.refine.pdf.model

    analysis: Analysis = prompt.update(
        cache_dir=p.directory / "prompt",
        prefix=model,
    )(
        client,
        messages=[
            Message(type="system", prompt=SYSTEM_MESSAGE),
            Message(type="application/pdf", prompt=p.pdf_path),
        ],
        model=model,
        structured_model=Analysis,
    ).parsed

    paper = Paper(
        title=None,
        authors=[
            PaperAuthor(
                display_name=str(author_affiliations.author),
                author=Author(name=str(author_affiliations.author)),
                affiliations=[
                    Institution(name=str(affiliation))
                    for affiliation in author_affiliations.affiliations
                ],
            )
            for author_affiliations in analysis.authors_affiliations
        ],
        links=[Link(type=type, link=link)],
    )
    return PaperInfo(paper=paper, key=key, info={"refined_by": {f"pdf-{model}": key}})
