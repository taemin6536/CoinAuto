"""Configuration template management utilities."""

import shutil
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class ConfigTemplateManager:
    """Manages configuration templates and template generation."""
    
    def __init__(self, templates_dir: str = "config/templates"):
        """Initialize template manager.
        
        Args:
            templates_dir: Directory containing configuration templates
        """
        self.templates_dir = Path(templates_dir)
        self.available_templates = self._discover_templates()
    
    def _discover_templates(self) -> Dict[str, Path]:
        """Discover available configuration templates."""
        templates = {}
        
        if not self.templates_dir.exists():
            logger.warning(f"Templates directory not found: {self.templates_dir}")
            return templates
        
        for template_file in self.templates_dir.glob("*.yaml"):
            template_name = template_file.stem
            templates[template_name] = template_file
            
        logger.info(f"Discovered {len(templates)} configuration templates")
        return templates
    
    def list_templates(self) -> List[str]:
        """Get list of available template names."""
        return list(self.available_templates.keys())
    
    def get_template_path(self, template_name: str) -> Optional[Path]:
        """Get path to a specific template.
        
        Args:
            template_name: Name of the template
            
        Returns:
            Path to template file or None if not found
        """
        return self.available_templates.get(template_name)
    
    def copy_template(self, template_name: str, destination: str, overwrite: bool = False) -> bool:
        """Copy a template to a destination path.
        
        Args:
            template_name: Name of the template to copy
            destination: Destination path for the copied template
            overwrite: Whether to overwrite existing files
            
        Returns:
            True if successful, False otherwise
        """
        template_path = self.get_template_path(template_name)
        if not template_path:
            logger.error(f"Template '{template_name}' not found")
            return False
        
        dest_path = Path(destination)
        
        # Check if destination exists
        if dest_path.exists() and not overwrite:
            logger.error(f"Destination file already exists: {dest_path}")
            return False
        
        try:
            # Create destination directory if needed
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy template
            shutil.copy2(template_path, dest_path)
            logger.info(f"Copied template '{template_name}' to {dest_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to copy template '{template_name}': {e}")
            return False
    
    def create_config_from_template(self, template_name: str, config_path: str = "config/default.yaml", overwrite: bool = False) -> bool:
        """Create a configuration file from a template.
        
        Args:
            template_name: Name of the template to use
            config_path: Path where to create the configuration file
            overwrite: Whether to overwrite existing configuration
            
        Returns:
            True if successful, False otherwise
        """
        return self.copy_template(template_name, config_path, overwrite)
    
    def get_template_description(self, template_name: str) -> str:
        """Get description of a template based on its name and content.
        
        Args:
            template_name: Name of the template
            
        Returns:
            Description string
        """
        descriptions = {
            "minimal": "Minimal configuration with only essential settings",
            "development": "Development-friendly configuration with verbose logging and safe defaults",
            "production": "Production-ready configuration with conservative risk management",
            "default": "Standard configuration with balanced settings"
        }
        
        return descriptions.get(template_name, f"Configuration template: {template_name}")
    
    def validate_template(self, template_name: str) -> bool:
        """Validate that a template is properly formatted.
        
        Args:
            template_name: Name of the template to validate
            
        Returns:
            True if valid, False otherwise
        """
        template_path = self.get_template_path(template_name)
        if not template_path:
            return False
        
        try:
            # Import here to avoid circular imports
            from .manager import ConfigManager
            
            # Create temporary config manager to validate template
            temp_manager = ConfigManager(str(template_path), enable_hot_reload=False)
            temp_manager.load_config()
            return True
            
        except Exception as e:
            logger.error(f"Template '{template_name}' validation failed: {e}")
            return False
    
    def create_custom_template(self, template_name: str, base_template: str = "default", modifications: Dict = None) -> bool:
        """Create a custom template based on an existing template.
        
        Args:
            template_name: Name for the new template
            base_template: Base template to modify
            modifications: Dictionary of modifications to apply
            
        Returns:
            True if successful, False otherwise
        """
        # This is a placeholder for future enhancement
        # Could implement YAML merging and modification logic
        logger.info(f"Custom template creation not yet implemented: {template_name}")
        return False


# Global template manager instance
template_manager = ConfigTemplateManager()


def list_available_templates() -> List[str]:
    """Get list of available configuration templates."""
    return template_manager.list_templates()


def create_config_from_template(template_name: str, config_path: str = "config/default.yaml", overwrite: bool = False) -> bool:
    """Create a configuration file from a template.
    
    Args:
        template_name: Name of the template to use
        config_path: Path where to create the configuration file
        overwrite: Whether to overwrite existing configuration
        
    Returns:
        True if successful, False otherwise
    """
    return template_manager.create_config_from_template(template_name, config_path, overwrite)


def get_template_info() -> Dict[str, str]:
    """Get information about all available templates.
    
    Returns:
        Dictionary mapping template names to descriptions
    """
    templates = template_manager.list_templates()
    return {name: template_manager.get_template_description(name) for name in templates}