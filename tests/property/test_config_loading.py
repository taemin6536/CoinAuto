"""Property-based tests for configuration loading reliability.

**Feature: upbit-trading-bot, Property 10: Configuration Loading Reliability**
**Validates: Requirements 3.4, 7.1**
"""

import pytest
import tempfile
import yaml
from pathlib import Path
from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import composite

from upbit_trading_bot.config import ConfigManager, ConfigValidationError


@composite
def valid_config_data(draw):
    """Generate valid configuration data structure."""
    # Generate API section
    api_config = {
        'base_url': draw(st.sampled_from([
            'https://api.upbit.com',
            'https://api-test.upbit.com'
        ])),
        'websocket_url': draw(st.sampled_from([
            'wss://api.upbit.com/websocket/v1',
            'wss://api-test.upbit.com/websocket/v1'
        ])),
        'timeout': draw(st.integers(min_value=1, max_value=300)),
        'max_retries': draw(st.integers(min_value=1, max_value=10)),
        'retry_delay': draw(st.floats(min_value=0.1, max_value=10.0))
    }
    
    # Generate trading section
    trading_config = {
        'enabled': draw(st.booleans()),
        'default_market': draw(st.sampled_from([
            'KRW-BTC', 'KRW-ETH', 'KRW-ADA', 'KRW-DOT'
        ])),
        'order_type': draw(st.sampled_from(['limit', 'market'])),
        'min_order_amount': draw(st.integers(min_value=1000, max_value=50000)),
        'max_position_size': draw(st.floats(min_value=0.01, max_value=1.0))
    }
    
    # Generate risk section
    risk_config = {
        'stop_loss_percentage': draw(st.floats(min_value=0.01, max_value=0.5)),
        'daily_loss_limit': draw(st.floats(min_value=0.01, max_value=0.2)),
        'max_daily_trades': draw(st.integers(min_value=1, max_value=1000)),
        'min_balance_threshold': draw(st.integers(min_value=1000, max_value=100000)),
        'position_size_limit': draw(st.floats(min_value=0.01, max_value=1.0))
    }
    
    # Generate strategies section with random strategy names
    strategy_names = draw(st.lists(
        st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')), 
                min_size=3, max_size=20),
        min_size=0, max_size=5, unique=True
    ))
    
    strategies_config = {
        'enabled': strategy_names,
        'evaluation_interval': draw(st.integers(min_value=1, max_value=3600)),
        'signal_threshold': draw(st.floats(min_value=0.1, max_value=1.0))
    }
    
    # Add individual strategy configurations
    for strategy_name in strategy_names:
        strategies_config[strategy_name] = {
            'param1': draw(st.floats(min_value=0.1, max_value=10.0)),
            'param2': draw(st.integers(min_value=1, max_value=100)),
            'enabled': draw(st.booleans())
        }
    
    return {
        'api': api_config,
        'trading': trading_config,
        'risk': risk_config,
        'strategies': strategies_config
    }


@composite
def invalid_config_data(draw):
    """Generate invalid configuration data for negative testing."""
    invalid_type = draw(st.sampled_from([
        'string_instead_of_dict',
        'list_instead_of_dict',
        'missing_required_section',
        'invalid_section_type'
    ]))
    
    if invalid_type == 'string_instead_of_dict':
        return "this should be a dictionary"
    elif invalid_type == 'list_instead_of_dict':
        return ['this', 'should', 'be', 'a', 'dictionary']
    elif invalid_type == 'missing_required_section':
        # Return config missing one of the required sections
        valid_config = draw(valid_config_data())
        section_to_remove = draw(st.sampled_from(['api', 'trading', 'risk', 'strategies']))
        del valid_config[section_to_remove]
        return valid_config
    elif invalid_type == 'invalid_section_type':
        # Return config with invalid section type
        valid_config = draw(valid_config_data())
        section_to_break = draw(st.sampled_from(['api', 'trading', 'risk', 'strategies']))
        valid_config[section_to_break] = "this should be a dict"
        return valid_config


class TestConfigurationLoadingReliability:
    """Property-based tests for configuration loading reliability."""
    
    @given(config_data=valid_config_data())
    @settings(max_examples=100)
    def test_property_10_configuration_loading_reliability(self, config_data):
        """
        **Feature: upbit-trading-bot, Property 10: Configuration Loading Reliability**
        **Validates: Requirements 3.4, 7.1**
        
        Property: For any valid YAML configuration file, all strategy parameters 
        should be loaded correctly and applied to strategies.
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f, default_flow_style=False)
            temp_config_path = f.name
        
        try:
            # Test that ConfigManager can load the configuration
            config_manager = ConfigManager(temp_config_path)
            loaded_config = config_manager.load_config()
            
            # Property 1: Loaded config should match original data
            assert loaded_config == config_data, "Loaded configuration should match original data"
            
            # Property 2: All required sections should be present
            required_sections = ['api', 'trading', 'risk', 'strategies']
            for section in required_sections:
                assert section in loaded_config, f"Required section '{section}' should be present"
                assert isinstance(loaded_config[section], dict), f"Section '{section}' should be a dictionary"
            
            # Property 3: Strategy parameters should be accessible
            strategies_config = config_manager.get_section('strategies')
            assert 'enabled' in strategies_config, "Strategies section should have 'enabled' key"
            assert 'evaluation_interval' in strategies_config, "Strategies section should have 'evaluation_interval' key"
            assert 'signal_threshold' in strategies_config, "Strategies section should have 'signal_threshold' key"
            
            # Property 4: Individual strategy configurations should be retrievable
            enabled_strategies = strategies_config.get('enabled', [])
            for strategy_name in enabled_strategies:
                strategy_config = config_manager.get_strategy_config(strategy_name)
                # Strategy config should be a dictionary (even if empty)
                assert isinstance(strategy_config, dict), f"Strategy '{strategy_name}' config should be a dictionary"
                
                # If strategy has specific config, it should match what was in the original
                if strategy_name in config_data['strategies']:
                    expected_strategy_config = config_data['strategies'][strategy_name]
                    assert strategy_config == expected_strategy_config, f"Strategy '{strategy_name}' config should match original"
            
            # Property 5: Config manager should report as loaded
            assert config_manager._loaded, "ConfigManager should report as loaded after successful load"
            
            # Property 6: get_config() should return the same data
            retrieved_config = config_manager.get_config()
            assert retrieved_config == loaded_config, "get_config() should return the same data as load_config()"
            
        finally:
            # Clean up temporary file
            Path(temp_config_path).unlink(missing_ok=True)
    
    @given(invalid_data=invalid_config_data())
    @settings(max_examples=50)
    def test_invalid_config_handling(self, invalid_data):
        """Test that invalid configurations are properly rejected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_data, f, default_flow_style=False)
            temp_config_path = f.name
        
        try:
            config_manager = ConfigManager(temp_config_path)
            
            # Should raise ConfigValidationError for invalid configurations
            with pytest.raises(ConfigValidationError):
                config_manager.load_config()
                
        finally:
            # Clean up temporary file
            Path(temp_config_path).unlink(missing_ok=True)
    
    def test_nonexistent_config_file(self):
        """Test handling of nonexistent configuration files."""
        config_manager = ConfigManager("nonexistent_file.yaml")
        
        with pytest.raises(ConfigValidationError) as exc_info:
            config_manager.load_config()
        
        assert "not found" in str(exc_info.value).lower()
    
    def test_empty_config_file(self):
        """Test handling of empty configuration files."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("")  # Empty file
            temp_config_path = f.name
        
        try:
            config_manager = ConfigManager(temp_config_path)
            
            with pytest.raises(ConfigValidationError) as exc_info:
                config_manager.load_config()
            
            assert "empty" in str(exc_info.value).lower()
            
        finally:
            Path(temp_config_path).unlink(missing_ok=True)
    
    def test_malformed_yaml(self):
        """Test handling of malformed YAML files."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [unclosed")  # Malformed YAML
            temp_config_path = f.name
        
        try:
            config_manager = ConfigManager(temp_config_path)
            
            with pytest.raises(ConfigValidationError) as exc_info:
                config_manager.load_config()
            
            assert "yaml" in str(exc_info.value).lower()
            
        finally:
            Path(temp_config_path).unlink(missing_ok=True)