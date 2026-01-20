import hashlib
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Any, Type

from outsight import send
from paperazzi.platforms.utils import Message
from paperazzi.utils import DiskStoreFunc
from requests import HTTPError
from serieux import Comment

from .config import config
from .prompt import ParsedResponseSerializer


@dataclass
class Explained:
    # A detailed explanation for the choice of the value
    reasoning: str
    # The best literal quote from the paper which supports the value
    quote: str

    def __class_getitem__(cls, t):
        return Annotated[t, Comment(cls, required=True)]


def prompt_wrapper(prompt: DiskStoreFunc, *, force=False, send_input, **kwargs):
    model = kwargs["model"]
    structured_model = kwargs["structured_model"]

    exists, cache_file = prompt.exists(**kwargs)
    tmp_cache_file = None
    if force and exists:
        prompt = prompt.update(prefix=f".{prompt.info.store.prefix}")
        _, tmp_cache_file = prompt.exists(**kwargs)
        tmp_cache_file.unlink(missing_ok=True)

    try:
        value = prompt(**kwargs)
        if force or not exists:
            send(
                prompt=structured_model.__module__,
                model=model,
                input=send_input,
                input_tokens=value._.input_tokens,
                output_tokens=value._.output_tokens,
                tokens=value._.total_tokens,
            )
        return value
    finally:
        if tmp_cache_file and tmp_cache_file.exists():
            tmp_cache_file.rename(cache_file)


def prompt_html(
    system_prompt: str,
    first_message: str,
    structured_model: type[Any],
    link: str,
    send_input: str = None,
    force: bool = False,
) -> Type[Any]:
    def _make_key(_, kwargs: dict) -> str:
        kwargs = kwargs.copy()
        kwargs["messages"] = kwargs["messages"][:]
        for i, message in enumerate(kwargs["messages"]):
            message: Message
            if message.prompt == first_message:
                # Use only the link hash to compute the key. We do not expect the
                # html_content to change much so most of the time we will not need
                # to re-run the prompt.
                kwargs["messages"][i] = Message(
                    type=message.type,
                    prompt=message.prompt,
                )

        return config.refine.prompt._make_key(None, kwargs)

    cache_dir = config.data_path / "html" / hashlib.sha256(link.encode()).hexdigest()

    try:
        html_content = config.fetch.read(
            link,
            format="txt",
            cache_into=cache_dir / "content.html",
            cache_expiry=timedelta(days=6),
        )
    except HTTPError as exc:
        if exc.response.status_code == 404:
            return None
        else:
            raise

    prompt = config.refine.prompt.prompt.update(
        serializer=ParsedResponseSerializer[structured_model],
        cache_dir=cache_dir / "prompt",
        make_key=_make_key,
        prefix=config.refine.prompt.model,
        index=0,
    )

    return prompt_wrapper(
        prompt,
        force=force,
        send_input=send_input or link,
        client=config.refine.prompt.client,
        messages=[
            Message(type="system", prompt=system_prompt),
            Message(type="user", prompt=first_message, args=(html_content,)),
        ],
        model=config.refine.prompt.model,
        structured_model=structured_model,
    )
