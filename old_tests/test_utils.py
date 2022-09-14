from paperoni.display import asciiify, group_by, normalize, print_field


def test_asciiify():
    assert asciiify("Le café est brûlant") == "Le cafe est brulant"
    assert asciiify("cool ↔ beans") == "cool  beans"


def test_normalize():
    assert normalize(None) is None
    assert normalize("Le café est brûlant") == "le cafe est brulant"
    assert normalize("cool ↔ beans") == "cool  beans"


def test_group_by():
    numbers = [-1, 9, 73, 0, -91, 0, -8]
    grp = group_by(numbers, key=lambda x: x < 0)
    assert grp == {
        True: [-1, -91, -8],
        False: [9, 73, 0, 0],
    }
