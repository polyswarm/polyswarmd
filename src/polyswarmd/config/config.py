from abc import ABC, abstractmethod
from typing import Any, Dict


class Config(ABC):
    sub_config: 'Config'

    def __init__(self, config: Dict[str, Any], module=None):
        self.populate(config, module)
        self.finish()

    @abstractmethod
    def finish(self):
        raise NotImplementedError

    def populate(self, config: Dict[str, Any], module):
        for k, v in config.items():
            if not isinstance(v, dict):
                setattr(self, k, v)
            else:
                if module and hasattr(module, k.capitalize()):
                    sub_config = getattr(module, k.capitalize())
                    if issubclass(sub_config, Config):
                        setattr(self, k, sub_config(v, module))
