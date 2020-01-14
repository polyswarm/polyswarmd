from abc import ABC, abstractmethod
import os
import typing
from typing import Any, Dict, Optional, Tuple


class Config(ABC):
    module: Optional[Any]
    config: Dict[str, Any]

    def __init__(self, config: Dict[str, Any], module=None):
        self.module = module
        self.config = config

    @abstractmethod
    def finish(self):
        """
        Do any finalization steps for this Config
        Steps
        * cast any excepted ints, or bools because they be strings from the environment
        * load any defaults
        * initialize any objects that depend on the stored config values
        """
        raise NotImplementedError

    def correct_type(self, key: str, value: Any) -> Any:
        cast = typing.get_type_hints(self.__class__).get(key)
        if cast and cast in [int, str, bool]:
            return cast(value)
        else:
            return value

    def load(self):
        self.populate()
        self.finish()

    def populate(self):
        for k, v in self.config.items():
            if not isinstance(v, dict):
                setattr(self, k, self.correct_type(k, v))
            elif self.module and hasattr(self.module, k.capitalize()):
                sub_config_class = getattr(self.module, k.capitalize())
                if issubclass(sub_config_class, Config):
                    sub_config = sub_config_class(v, self.module)
                    setattr(self, k, sub_config)
                    sub_config.load()

    def overlay_and_load(self):
        self.overlay_environment()
        self.load()

    def overlay_environment(self):
        name = self.__class__.__name__.upper()
        for key, value in os.environ.items():
            if key.startswith(name):
                self.overlay_matching_value(key.replace(f'{name}_', ''), value)

    def overlay_matching_value(self, key, value):
        current = self.config
        rest = key
        while True:
            title, rest = Config.split(rest)
            if self.module and hasattr(self.module, title.capitalize()):
                found_value = current.get(title)
                if found_value and isinstance(found_value, dict):
                    current = found_value
                else:
                    current[title] = {}
                    current = current[title]
            else:
                # Not a sub config, just store the value
                current['_'.join([title, rest.lower()]) if rest else title] = value
                break

    @staticmethod
    def split(key: str) -> Tuple[str, str]:
        separated = key.split('_', 1)
        title = separated[0].lower()
        rest = separated[1] if len(separated) > 1 else ''
        return title, rest
