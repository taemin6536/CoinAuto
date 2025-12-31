"""
Test basic project structure and imports.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path for testing
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_project_structure():
    """Test that all required directories and files exist."""
    project_root = Path(__file__).parent.parent.parent
    
    # Check main package structure
    assert (project_root / "upbit_trading_bot" / "__init__.py").exists()
    assert (project_root / "upbit_trading_bot" / "main.py").exists()
    
    # Check subpackages
    subpackages = [
        "api", "data", "strategy", "order", 
        "risk", "portfolio", "config", "utils"
    ]
    
    for package in subpackages:
        package_path = project_root / "upbit_trading_bot" / package / "__init__.py"
        assert package_path.exists(), f"Missing package: {package}"
    
    # Check configuration files
    assert (project_root / "config" / "default.yaml").exists()
    assert (project_root / "config" / "strategies" / "sma_crossover.yaml").exists()
    assert (project_root / "config" / "strategies" / "rsi_momentum.yaml").exists()
    
    # Check project files
    assert (project_root / "requirements.txt").exists()
    assert (project_root / "setup.py").exists()
    assert (project_root / "pyproject.toml").exists()
    assert (project_root / "README.md").exists()


def test_package_imports():
    """Test that main package can be imported."""
    try:
        import upbit_trading_bot
        assert upbit_trading_bot.__version__ == "0.1.0"
    except ImportError as e:
        pytest.fail(f"Failed to import main package: {e}")


def test_main_module_import():
    """Test that main module can be imported."""
    try:
        from upbit_trading_bot import main
        assert hasattr(main, 'main')
        assert callable(main.main)
    except ImportError as e:
        pytest.fail(f"Failed to import main module: {e}")


def test_subpackage_imports():
    """Test that all subpackages can be imported."""
    subpackages = [
        "upbit_trading_bot.api",
        "upbit_trading_bot.data", 
        "upbit_trading_bot.strategy",
        "upbit_trading_bot.order",
        "upbit_trading_bot.risk",
        "upbit_trading_bot.portfolio",
        "upbit_trading_bot.config",
        "upbit_trading_bot.utils"
    ]
    
    for package in subpackages:
        try:
            __import__(package)
        except ImportError as e:
            pytest.fail(f"Failed to import {package}: {e}")


if __name__ == "__main__":
    pytest.main([__file__])