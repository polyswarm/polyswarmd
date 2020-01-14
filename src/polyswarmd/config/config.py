import os
from abc import abstractmethod, ABC
from typing import Dict, Any, ClassVar


class Config(ABC):
    def __init__(self, config: Dict[str, Any], module=None):
        self.overlay(self.__class__.__name__, config, module)
        self.populate(config, module)
        self.finish()

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

    def populate(self, config: Dict[str, Any], module):
        for k, v in config.items():
            if not isinstance(v, dict):
                setattr(self, k, v)
            else:
                if module and hasattr(module, k.capitalize()):
                    sub_config: ClassVar[Config] = getattr(module, k.capitalize())
                    if issubclass(sub_config, Config):
                        setattr(self, k, sub_config(v, module))

    @staticmethod
    def overlay(root, config: Dict[str, Any], module=None):
        for k, v in os.environ.items():
            parts = k.split("_", 1)
            title = parts[0]
            if title.lower() != root.lower():
                continue

            level = config
            while True:
                parts = parts[1].split("_", 1)
                # See if this can be loaded as is
                if module and hasattr(module, parts[0].capitalize()):
                    # remove from parts, since it is part of the path
                    found_config = level.get(parts[0].lower())
                    if found_config is not None and isinstance(found_config, dict):
                        level = found_config
                    else:
                        level[parts[0].lower()] = {}
                        level = level.get(parts[0].lower())
                else:
                    # Not a sub config, just store the value
                    if len(parts) > 1:
                        level['_'.join([parts[0].lower(), parts[1].lower()])] = v
                    else:
                        level[parts[0].lower()] = v
                    break
