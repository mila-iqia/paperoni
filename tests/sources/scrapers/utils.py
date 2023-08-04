from ovld import ovld


def controller_from_generator(genfn):
    gen = genfn()
    next(gen)

    def controller(author, paper):
        return gen.send((author, paper))

    return controller


@ovld
def sort_data(d: dict):
    return dict(sorted([(k, sort_data(v)) for k, v in d.items()]))


@ovld
def sort_data(li: list):
    return sorted(li, key=lambda x: str(x))


@ovld
def sort_data(obj: object):
    return obj


def isin(
    data_regression, results, ignore=[], basename=None, sort=False, **filter
):
    for r in results:
        if any(getattr(r, k) != v for k, v in filter.items()):
            continue
        r = r.tagged_dict()
        if sort:
            # Sort the data to avoid non-deterministic ordering issues
            r = sort_data(r)
        for k in ignore:
            del r[k]
        data_regression.check(r, basename=basename)
        break
    else:
        raise Exception(f"No data found that corresponds to {filter}")
    return True
