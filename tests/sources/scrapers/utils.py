def controller_from_generator(genfn):
    gen = genfn()
    next(gen)

    def controller(author, paper):
        return gen.send((author, paper))

    return controller


def isin(data_regression, results, ignore=[], basename=None, **filter):
    for r in results:
        if any(getattr(r, k) != v for k, v in filter.items()):
            continue
        r = r.tagged_dict()
        for k in ignore:
            del r[k]
        data_regression.check(r, basename=basename)
        break
    else:
        raise Exception(f"No data found that corresponds to {filter}")
    return True
