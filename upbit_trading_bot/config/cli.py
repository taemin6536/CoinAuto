"""Command-line interface for configuration management."""

import click
import sys
from pathlib import Path
from typing import Optional

from .manager import ConfigManager, ConfigValidationError
from .templates import template_manager


@click.group()
def config():
    """Configuration management commands."""
    pass


@config.command()
@click.option('--config-path', '-c', default='config/default.yaml', help='Path to configuration file')
def validate(config_path: str):
    """Validate a configuration file."""
    click.echo(f"Validating configuration: {config_path}")
    
    try:
        manager = ConfigManager(config_path, enable_hot_reload=False)
        manager.load_config()
        click.echo(click.style("✓ Configuration is valid", fg='green'))
        
        # Show configuration summary
        config = manager.get_config()
        click.echo("\nConfiguration Summary:")
        click.echo(f"  Trading enabled: {config.get('trading', {}).get('enabled', False)}")
        click.echo(f"  Default market: {config.get('trading', {}).get('default_market', 'N/A')}")
        
        strategies = config.get('strategies', {})
        enabled_strategies = strategies.get('enabled', [])
        click.echo(f"  Enabled strategies: {', '.join(enabled_strategies) if enabled_strategies else 'None'}")
        
        risk = config.get('risk', {})
        click.echo(f"  Stop loss: {risk.get('stop_loss_percentage', 0) * 100:.1f}%")
        click.echo(f"  Daily loss limit: {risk.get('daily_loss_limit', 0) * 100:.1f}%")
        
    except ConfigValidationError as e:
        click.echo(click.style(f"✗ Configuration validation failed:", fg='red'))
        click.echo(f"  Error: {e.message}")
        if e.field_path:
            click.echo(f"  Field: {e.field_path}")
        if e.expected_type and e.actual_value:
            click.echo(f"  Expected: {e.expected_type}, Got: {e.actual_value}")
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"✗ Unexpected error: {e}", fg='red'))
        sys.exit(1)


@config.command()
def templates():
    """List available configuration templates."""
    available_templates = template_manager.list_templates()
    
    if not available_templates:
        click.echo("No configuration templates found.")
        return
    
    click.echo("Available configuration templates:")
    for template_name in sorted(available_templates):
        description = template_manager.get_template_description(template_name)
        click.echo(f"  {template_name}: {description}")


@config.command()
@click.argument('template_name')
@click.option('--output', '-o', default='config/default.yaml', help='Output path for configuration file')
@click.option('--overwrite', is_flag=True, help='Overwrite existing configuration file')
def create(template_name: str, output: str, overwrite: bool):
    """Create a configuration file from a template."""
    if template_name not in template_manager.list_templates():
        click.echo(click.style(f"✗ Template '{template_name}' not found", fg='red'))
        click.echo("Available templates:")
        for name in template_manager.list_templates():
            click.echo(f"  - {name}")
        sys.exit(1)
    
    output_path = Path(output)
    if output_path.exists() and not overwrite:
        click.echo(click.style(f"✗ Configuration file already exists: {output}", fg='red'))
        click.echo("Use --overwrite to replace existing file")
        sys.exit(1)
    
    if template_manager.copy_template(template_name, output, overwrite):
        click.echo(click.style(f"✓ Created configuration from template '{template_name}': {output}", fg='green'))
        
        # Validate the created configuration
        try:
            manager = ConfigManager(output, enable_hot_reload=False)
            manager.load_config()
            click.echo(click.style("✓ Generated configuration is valid", fg='green'))
        except Exception as e:
            click.echo(click.style(f"⚠ Warning: Generated configuration has issues: {e}", fg='yellow'))
    else:
        click.echo(click.style(f"✗ Failed to create configuration from template '{template_name}'", fg='red'))
        sys.exit(1)


@config.command()
@click.argument('strategy_name')
@click.option('--config-path', '-c', default='config/default.yaml', help='Path to main configuration file')
def check_strategy(strategy_name: str, config_path: str):
    """Check if a strategy is properly configured."""
    try:
        manager = ConfigManager(config_path, enable_hot_reload=False)
        manager.load_config()
        
        # Check if strategy is enabled
        enabled_strategies = manager.get_enabled_strategies()
        is_enabled = strategy_name in enabled_strategies
        
        # Check if strategy config exists
        strategy_config = manager.get_strategy_config(strategy_name)
        has_config = bool(strategy_config)
        
        click.echo(f"Strategy: {strategy_name}")
        click.echo(f"  Enabled: {click.style('Yes' if is_enabled else 'No', fg='green' if is_enabled else 'red')}")
        click.echo(f"  Configuration: {click.style('Found' if has_config else 'Not found', fg='green' if has_config else 'red')}")
        
        if has_config:
            strategy_info = strategy_config.get('strategy', {})
            click.echo(f"  Description: {strategy_info.get('description', 'N/A')}")
            click.echo(f"  Strategy enabled in file: {strategy_info.get('enabled', False)}")
            
            # Show key parameters
            params = strategy_config.get('parameters', {})
            if params:
                click.echo("  Key parameters:")
                for key, value in list(params.items())[:5]:  # Show first 5 parameters
                    click.echo(f"    {key}: {value}")
                if len(params) > 5:
                    click.echo(f"    ... and {len(params) - 5} more")
        
        if not is_enabled and has_config:
            click.echo(click.style("⚠ Strategy has configuration but is not enabled", fg='yellow'))
        elif is_enabled and not has_config:
            click.echo(click.style("⚠ Strategy is enabled but configuration not found", fg='yellow'))
            
    except Exception as e:
        click.echo(click.style(f"✗ Error checking strategy: {e}", fg='red'))
        sys.exit(1)


@config.command()
@click.option('--config-path', '-c', default='config/default.yaml', help='Path to configuration file')
@click.option('--watch', '-w', is_flag=True, help='Watch for configuration changes')
def monitor(config_path: str, watch: bool):
    """Monitor configuration and show current status."""
    try:
        manager = ConfigManager(config_path, enable_hot_reload=watch)
        
        def show_status():
            config = manager.get_config()
            click.clear()
            click.echo("=== Trading Bot Configuration Status ===")
            click.echo(f"Configuration file: {config_path}")
            click.echo(f"Last loaded: {click.style('Just now', fg='green')}")
            
            # Trading status
            trading = config.get('trading', {})
            trading_enabled = trading.get('enabled', False)
            click.echo(f"Trading: {click.style('ENABLED' if trading_enabled else 'DISABLED', fg='green' if trading_enabled else 'red')}")
            
            # Strategies
            strategies = config.get('strategies', {})
            enabled_strategies = strategies.get('enabled', [])
            click.echo(f"Active strategies: {', '.join(enabled_strategies) if enabled_strategies else 'None'}")
            
            # Risk settings
            risk = config.get('risk', {})
            click.echo(f"Stop loss: {risk.get('stop_loss_percentage', 0) * 100:.1f}%")
            click.echo(f"Daily loss limit: {risk.get('daily_loss_limit', 0) * 100:.1f}%")
            
            if watch:
                click.echo("\nWatching for changes... Press Ctrl+C to exit")
        
        if watch:
            # Add callback to refresh display on changes
            def on_config_change(config_type: str, new_config: dict):
                show_status()
            
            manager.add_change_callback(on_config_change)
        
        show_status()
        
        if watch:
            try:
                while True:
                    click.pause()
            except KeyboardInterrupt:
                click.echo("\nStopping configuration monitor...")
                manager.stop_hot_reload()
        
    except Exception as e:
        click.echo(click.style(f"✗ Error monitoring configuration: {e}", fg='red'))
        sys.exit(1)


if __name__ == '__main__':
    config()