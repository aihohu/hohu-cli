"""
HoHu CLI 配置模块
集中管理所有配置相关的功能
"""

from hohu.config.components import (
    COMPONENT_CONFIG,
    get_all_components,
    get_component_color,
    get_component_config,
    get_component_dev_cmd,
    get_component_fallback_cmd,
    get_component_folder,
    get_component_install_cmd,
    get_component_repo,
)

__all__ = [
    "COMPONENT_CONFIG",
    "get_all_components",
    "get_component_color",
    "get_component_config",
    "get_component_dev_cmd",
    "get_component_fallback_cmd",
    "get_component_folder",
    "get_component_install_cmd",
    "get_component_repo",
]
