from abc import abstractmethod, ABC
from typing import Dict, Any


class Config(ABC):
    def __init__(self, config: Dict[str, Any], module=None):
        self.populate(config)
        self.module = module
        self.finish()

    @abstractmethod
    def finish(self):
        raise NotImplementedError

    def populate(self, config):
        for k, v in config.items():
            if not isinstance(v, dict):
                setattr(self, k, v)
            else:
                if self.module and hasattr(self.module, k.capitalize()):
                    sub_config = getattr(self.module, k.capitalize())
                    if type(sub_config) is Config:
                        setattr(self, k, sub_config(v, self.module))
