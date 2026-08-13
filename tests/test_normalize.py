from core.normalize import normalize_publisher


def test_normalize_publisher_splits_concatenated_place():
    assert normalize_publisher("Oxford University PressOxford") == "Oxford University Press, Oxford"


def test_normalize_publisher_leaves_normal_names_untouched():
    assert normalize_publisher("Elsevier") == "Elsevier"
    assert normalize_publisher("F.A. Davis") == "F.A. Davis"
    assert normalize_publisher("Taylor & Francis") == "Taylor & Francis"


def test_normalize_publisher_handles_none_and_empty():
    assert normalize_publisher(None) is None
    assert normalize_publisher("") == ""


def test_normalize_publisher_handles_multiple_concatenations():
    assert normalize_publisher("SpringerBerlinHeidelberg") == "Springer, Berlin, Heidelberg"
