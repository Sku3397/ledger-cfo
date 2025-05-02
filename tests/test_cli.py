from ledger_cfo.__main__ import app  # Import app from __main__

# Note: The previous test tried to run cli.main or __main__.main, which don't exist.
# Testing the Flask app object import for now.


def test_cli_app_import():
    """Test that the Flask app object can be imported."""
    assert app is not None
