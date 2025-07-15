import pytest
from serieux import serialize

from paperoni.model.classes import Institution
from paperoni.refinement.formats import institution_from_ror

rors = {
    "mila": "05c22rx21",
    "udem": "0161xgx34",
    "mcgill": "01pxwe438",
}


@pytest.mark.parametrize("name,ror_id", rors.items())
def test_ror(name, ror_id, data_regression):
    inst = institution_from_ror(ror_id)
    data = serialize(Institution, inst)
    data_regression.check(data)
