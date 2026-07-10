from app.routers.files import safe_filename


def test_safe_filename_strips_path():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename(r"..\..\secret.txt") == "secret.txt"


def test_safe_filename_handles_none_and_empty():
    assert safe_filename(None) == "unnamed"
    assert safe_filename("") == "unnamed"
    assert safe_filename("/") == "unnamed"
