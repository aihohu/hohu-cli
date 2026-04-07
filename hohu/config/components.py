"""
统一的组件配置模块
集中管理所有组件相关的配置信息，避免代码重复
"""

# 组件配置统一管理
COMPONENT_CONFIG = {
    "Backend": {
        "folder": "hohu-admin",
        "repo": "https://github.com/aihohu/hohu-admin.git",
        "install_cmd": ["uv", "sync"],
        "fallback_cmd": ["pip", "install", "-r", "requirements.txt"],
        "dev_cmd": ["uv", "run", "fastapi", "dev", "app/main.py"],
        "color": "green",
        "init_script": "scripts/init.py",
    },
    "Frontend": {
        "folder": "hohu-admin-web",
        "repo": "https://github.com/aihohu/hohu-admin-web.git",
        "install_cmd": ["pnpm", "install"],
        "fallback_cmd": ["npm", "install"],
        "dev_cmd": ["pnpm", "dev"],
        "color": "cyan",
    },
    "App": {
        "folder": "hohu-admin-app",
        "repo": "https://github.com/aihohu/hohu-admin-app.git",
        "install_cmd": ["pnpm", "install"],
        "fallback_cmd": ["npm", "install"],
        "dev_cmd": ["pnpm", "dev"],  # 基础命令，实际使用时根据target动态生成
        "color": "yellow",
    },
}


def get_component_config(component_name: str) -> dict:
    """
    获取指定组件的配置

    Args:
        component_name: 组件名称 ("Backend", "Frontend", "App")

    Returns:
        dict: 组件配置信息

    Raises:
        KeyError: 组件不存在时抛出
    """
    return COMPONENT_CONFIG[component_name]


def get_component_folder(component_name: str) -> str:
    """
    获取指定组件的文件夹名称

    Args:
        component_name: 组件名称

    Returns:
        str: 文件夹名称
    """
    return COMPONENT_CONFIG[component_name]["folder"]


def get_component_repo(component_name: str) -> str:
    """
    获取指定组件的仓库地址

    Args:
        component_name: 组件名称

    Returns:
        str: 仓库地址
    """
    return COMPONENT_CONFIG[component_name]["repo"]


def get_component_install_cmd(component_name: str) -> list[str]:
    """
    获取指定组件的安装命令

    Args:
        component_name: 组件名称

    Returns:
        list[str]: 安装命令
    """
    return COMPONENT_CONFIG[component_name]["install_cmd"]


def get_component_fallback_cmd(component_name: str) -> list[str] | None:
    """
    获取指定组件的备用安装命令

    Args:
        component_name: 组件名称

    Returns:
        list[str] | None: 备用安装命令
    """
    return COMPONENT_CONFIG[component_name].get("fallback_cmd")


def get_component_dev_cmd(component_name: str, target: str = "h5") -> list[str]:
    """
    获取指定组件的开发命令

    Args:
        component_name: 组件名称
        target: APP目标平台 (h5, mp, app)，仅对App组件有效

    Returns:
        list[str]: 开发命令
    """
    cmd = COMPONENT_CONFIG[component_name]["dev_cmd"].copy()
    # 对于App组件，根据target动态生成命令
    if component_name == "App" and target != "h5":
        cmd = ["pnpm", f"dev:{target}"]
    return cmd


def get_component_color(component_name: str) -> str:
    """
    获取指定组件的颜色标识

    Args:
        component_name: 组件名称

    Returns:
        str: Rich颜色名称
    """
    return COMPONENT_CONFIG[component_name]["color"]


def get_component_init_script(component_name: str) -> str | None:
    """
    获取指定组件的初始化脚本路径

    Args:
        component_name: 组件名称

    Returns:
        str | None: 初始化脚本相对路径，未配置则返回 None
    """
    return COMPONENT_CONFIG[component_name].get("init_script")


def get_all_components() -> list[str]:
    """
    获取所有可用的组件名称列表

    Returns:
        list[str]: 组件名称列表
    """
    return list(COMPONENT_CONFIG.keys())
