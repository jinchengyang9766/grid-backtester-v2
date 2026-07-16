"""Environment sanity check for the backend package."""

import importlib


def test_backend_package_is_importable() -> None:
    app = importlib.import_module("app")
    assert app is not None
    assert isinstance(app.__version__, str)
