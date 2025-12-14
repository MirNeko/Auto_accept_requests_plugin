from src.plugin_system.base.plugin_metadata import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="auto_accept_requests",
    description="自动同意请求插件",
    usage="启用后根据插件配置自动同意请求，可选通知发起人",
    version="1.0.0",
    author="MirNeko",
    license="GPL-v3.0-or-later",
    repository_url="https://github.com/MoFox-Studio",
    keywords=["qq", "napcat", "onebot", "request", "auto-accept"],
    categories=["management", "integration"],
    extra={"is_built_in": "false", "plugin_type": "functional"},
    dependencies=[],
    python_dependencies=[],
)

