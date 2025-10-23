from paperazzi.utils import DiskStoreFunc


def force_prompt(prompt: DiskStoreFunc, **kwargs: dict):
    _, cache_file = prompt.exists(**kwargs)
    tmp_prompt = prompt.update(prefix=f".{prompt.info.store.prefix}")
    _, tmp_cache_file = tmp_prompt.exists(**kwargs)
    tmp_cache_file.unlink(missing_ok=True)
    try:
        return tmp_prompt(**kwargs)
    finally:
        if tmp_cache_file.exists():
            tmp_cache_file.rename(cache_file)
