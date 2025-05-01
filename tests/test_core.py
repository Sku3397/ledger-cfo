import pytest
import ledger_cfo # Keep the import correction

def test_package_import():
    """Test that the main package can be imported."""
    assert ledger_cfo is not None 