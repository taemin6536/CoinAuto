"""Unit tests for configuration management functionality."""

import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from upbit_trading_bot.config.manager import ConfigManager, ConfigValidationError
from upbit_trading_bot.config.templates import ConfigTemplateManager


class TestConfigManager:
    """Test cases for ConfigManager."""
    
    def test_load_valid_config(self):
        """Test loading a valid configuration file."""
        manager = ConfigManager("config/default.yaml", enable_hot_reload=False)
        config = manager.load_config()
        
        assert isinstance(config, dict)
        assert "api" in config
        assert "trading" in config
        assert "risk" in config
        assert "strategies" in config
    
    def test_get_config_sections(self):
        """Test getting specific configuration sections."""
        manager = ConfigManager("config/default.yaml", enable_hot_reload=False)
        manager.load_config()
        
        api_config = manager.get_section("api")
        assert isinstance(api_config, dict)
        assert "base_url" in api_config
        
        trading_config = manager.get_section("trading")
        assert isinstance(trading_config, dict)
        assert "enabled" in trading_config
    
    def test_get_strategy_config(self):
        """Test getting strategy configuration."""
        manager = ConfigManager("config/default.yaml", enable_hot_reload=False)
        manager.load_config()
        
        # Test existing strategy
        sma_config = manager.get_strategy_config("sma_crossover")
        assert isinstance(sma_config, dict)
        if sma_config:  # If strategy file exists
            assert "strategy" in sma_config
            assert "parameters" in sma_config
        
        # Test non-existing strategy
        nonexistent_config = manager.get_strategy_config("nonexistent_strategy")
        assert isinstance(nonexistent_config, dict)
    
    def test_enabled_strategies(self):
        """Test getting enabled strategies."""
        manager = ConfigManager("config/default.yaml", enable_hot_reload=False)
        manager.load_config()
        
        enabled_strategies = manager.get_enabled_strategies()
        assert isinstance(enabled_strategies, list)
        
        # Test strategy enabled check
        for strategy in enabled_strategies:
            assert manager.is_strategy_enabled(strategy)
    
    def test_config_validation_missing_file(self):
        """Test configuration validation with missing file."""
        manager = ConfigManager("nonexistent.yaml", enable_hot_reload=False)
        
        with pytest.raises(ConfigValidationError) as exc_info:
            manager.load_config()
        
        assert "not found" in str(exc_info.value.message)
    
    def test_config_validation_invalid_yaml(self):
        """Test configuration validation with invalid YAML."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_path = f.name
        
        try:
            manager = ConfigManager(temp_path, enable_hot_reload=False)
            with pytest.raises(ConfigValidationError) as exc_info:
                manager.load_config()
            
            assert "Invalid YAML syntax" in str(exc_info.value.message)
        finally:
            Path(temp_path).unlink()
    
    def test_config_validation_missing_sections(self):
        """Test configuration validation with missing required sections."""
        config_data = {
            "api": {"base_url": "test"},
            # Missing required sections: trading, risk, strategies
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name
        
        try:
            manager = ConfigManager(temp_path, enable_hot_reload=False)
            with pytest.raises(ConfigValidationError) as exc_info:
                manager.load_config()
            
            assert "Missing required configuration section" in str(exc_info.value.message)
        finally:
            Path(temp_path).unlink()
    
    def test_config_validation_invalid_types(self):
        """Test configuration validation with invalid field types."""
        config_data = {
            "api": {
                "base_url": "https://api.upbit.com",
                "websocket_url": "wss://api.upbit.com/websocket/v1",
                "timeout": "invalid_number",  # Should be number
                "max_retries": 3,
                "retry_delay": 1.0
            },
            "trading": {
                "enabled": True,
                "default_market": "KRW-BTC",
                "order_type": "limit",
                "min_order_amount": 5000,
                "max_position_size": 0.1
            },
            "risk": {
                "stop_loss_percentage": 0.05,
                "daily_loss_limit": 0.02,
                "max_daily_trades": 50,
                "min_balance_threshold": 10000,
                "position_size_limit": 0.2
            },
            "strategies": {
                "enabled": [],
                "evaluation_interval": 60,
                "signal_threshold": 0.7
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name
        
        try:
            manager = ConfigManager(temp_path, enable_hot_reload=False)
            with pytest.raises(ConfigValidationError) as exc_info:
                manager.load_config()
            
            assert "must be of type" in str(exc_info.value.message)
            assert "timeout" in str(exc_info.value.field_path)
        finally:
            Path(temp_path).unlink()
    
    def test_config_validation_invalid_percentage(self):
        """Test configuration validation with invalid percentage values."""
        config_data = {
            "api": {
                "base_url": "https://api.upbit.com",
                "websocket_url": "wss://api.upbit.com/websocket/v1",
                "timeout": 30,
                "max_retries": 3,
                "retry_delay": 1.0
            },
            "trading": {
                "enabled": True,
                "default_market": "KRW-BTC",
                "order_type": "limit",
                "min_order_amount": 5000,
                "max_position_size": 0.1
            },
            "risk": {
                "stop_loss_percentage": 1.5,  # Invalid: > 1.0
                "daily_loss_limit": 0.02,
                "max_daily_trades": 50,
                "min_balance_threshold": 10000,
                "position_size_limit": 0.2
            },
            "strategies": {
                "enabled": [],
                "evaluation_interval": 60,
                "signal_threshold": 0.7
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name
        
        try:
            manager = ConfigManager(temp_path, enable_hot_reload=False)
            with pytest.raises(ConfigValidationError) as exc_info:
                manager.load_config()
            
            assert "must be between 0 and 1" in str(exc_info.value.message)
        finally:
            Path(temp_path).unlink()
    
    def test_reload_config(self):
        """Test manual configuration reload."""
        manager = ConfigManager("config/default.yaml", enable_hot_reload=False)
        manager.load_config()
        
        # Test successful reload
        result = manager.reload_config()
        assert result is True
    
    def test_validate_config_file(self):
        """Test configuration file validation."""
        manager = ConfigManager(enable_hot_reload=False)
        
        # Test valid config
        result = manager.validate_config_file("config/default.yaml")
        assert result is True
        
        # Test invalid config
        result = manager.validate_config_file("nonexistent.yaml")
        assert result is False
    
    @patch('upbit_trading_bot.config.manager.Observer')
    def test_hot_reload_setup(self, mock_observer):
        """Test hot reload setup."""
        mock_observer_instance = MagicMock()
        mock_observer.return_value = mock_observer_instance
        
        manager = ConfigManager("config/default.yaml", enable_hot_reload=True)
        
        # Verify observer was created and started
        mock_observer.assert_called_once()
        mock_observer_instance.start.assert_called_once()
    
    def test_hot_reload_disabled(self):
        """Test that hot reload can be disabled."""
        manager = ConfigManager("config/default.yaml", enable_hot_reload=False)
        
        # Should not have observer when disabled
        assert manager._observer is None
        assert manager._file_handler is None


class TestConfigTemplateManager:
    """Test cases for ConfigTemplateManager."""
    
    def test_discover_templates(self):
        """Test template discovery."""
        template_manager = ConfigTemplateManager("config/templates")
        templates = template_manager.list_templates()
        
        assert isinstance(templates, list)
        assert len(templates) > 0
        assert "minimal" in templates
        assert "development" in templates
        assert "production" in templates
    
    def test_get_template_path(self):
        """Test getting template path."""
        template_manager = ConfigTemplateManager("config/templates")
        
        # Test existing template
        path = template_manager.get_template_path("minimal")
        assert path is not None
        assert path.exists()
        
        # Test non-existing template
        path = template_manager.get_template_path("nonexistent")
        assert path is None
    
    def test_get_template_description(self):
        """Test getting template descriptions."""
        template_manager = ConfigTemplateManager("config/templates")
        
        description = template_manager.get_template_description("minimal")
        assert isinstance(description, str)
        assert len(description) > 0
        
        # Test unknown template
        description = template_manager.get_template_description("unknown")
        assert "unknown" in description
    
    def test_copy_template(self):
        """Test copying template to destination."""
        template_manager = ConfigTemplateManager("config/templates")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            dest_path = Path(temp_dir) / "test_config.yaml"
            
            # Test successful copy
            result = template_manager.copy_template("minimal", str(dest_path))
            assert result is True
            assert dest_path.exists()
            
            # Test copy without overwrite (should fail)
            result = template_manager.copy_template("minimal", str(dest_path), overwrite=False)
            assert result is False
            
            # Test copy with overwrite (should succeed)
            result = template_manager.copy_template("minimal", str(dest_path), overwrite=True)
            assert result is True
    
    def test_validate_template(self):
        """Test template validation."""
        template_manager = ConfigTemplateManager("config/templates")
        
        # Test valid templates
        for template_name in template_manager.list_templates():
            result = template_manager.validate_template(template_name)
            assert result is True, f"Template {template_name} should be valid"
        
        # Test non-existing template
        result = template_manager.validate_template("nonexistent")
        assert result is False