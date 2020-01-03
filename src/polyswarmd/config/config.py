from abc import abstractmethod, ABC
from typing import Dict, Any, ClassVar


class Config(ABC):
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
                    sub_config: ClassVar[Config] = getattr(module, k.capitalize())
                    if issubclass(sub_config, Config):
                        setattr(self, k, sub_config(v, module))
