import json
import locale
from pathlib import Path

from hohu.config import get_lang


class I18n:
    def __init__(self):
        self.lang = get_lang()
        self.locales = {}
        self._load_all_locales()

    def _load_all_locales(self):
        """动态加载 locales 文件夹下的所有 json 文件"""
        # 获取当前文件所在目录下的 locales 文件夹
        locales_dir = Path(__file__).parent / "locales"

        if not locales_dir.exists():
            # 兼容性处理：如果找不到，尝试在当前工作目录找（开发调试用）
            locales_dir = Path.cwd() / "hohu" / "locales"

        for json_file in locales_dir.glob("*.json"):
            try:
                with open(json_file, encoding="utf-8") as f:
                    # 使用文件名作为 key (例如 'en', 'zh')
                    self.locales[json_file.stem] = json.load(f)
            except Exception:
                continue

        # 兜底：如果连 en 都没加载到，给一个空字典防止 KeyError
        if "en" not in self.locales:
            self.locales["en"] = {}

    def t(self, key: str) -> str:
        """获取翻译，支持 auto 跟随系统"""
        target_lang = self.lang

        if target_lang == "auto":
            sys_lang = locale.getdefaultlocale()[0]
            target_lang = "zh" if sys_lang and "zh" in sys_lang else "en"

        # 优先找目标语言，找不到找英文，再找不到返回 key 本身
        lang_data = self.locales.get(target_lang, self.locales.get("en", {}))
        return lang_data.get(key, key)

    def refresh(self):
        """当语言配置改变时调用"""
        self.lang = get_lang()


i18n = I18n()
