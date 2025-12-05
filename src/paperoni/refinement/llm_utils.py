from outsight import send
from paperazzi.utils import DiskStoreFunc


def prompt_wrapper(prompt: DiskStoreFunc, *, force=False, input, **kwargs):
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
                input=input,
                tokens=value.usage_metadata.total_token_count,
            )
        return value
    finally:
        if tmp_cache_file and tmp_cache_file.exists():
            tmp_cache_file.rename(cache_file)
