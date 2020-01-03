POLYSWARMD_CONFIG_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "polyswarmd.json",
    "type": "object",
    "properties": {
        "artifact": {
            "type": "object",
            "properties": {
                "max_size": {"type": "integer"},
                "fallback_max_size": {"type": "integer"},
                "limit": {"type": "integer"},
                "library": {
                    "type": "object",
                    "properties": {
                        "module": {"type": "string"},
                        "class_name": {"type": "string"},
                        "args": {"type": "array"}
                    },
                    "required": ["module", "class_name"]
                }
            }
        },
        "community": {"type": "string"},
        "eth": {
            "type": "object",
            "properties": {
                "trace_transactions": {"type": "boolean"},
                "filename": {"type": "string"},
                "consul": {
                    "type": "object",
                    "properties": {
                        "uri": {"type": "string"}
                    },
                    "required": ["uri"]
                }
            }
        },
        "profiler": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "db_uri": {"type": "string"}
            }
        },
        "redis": {
            "type": "object",
            "properties": {
              "uri": {"type": "string"}
            }
        },
        "websocket" : {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"}
            }
        }
    },
    "additionalItems": True,
    "required": ["community", "eth", "artifact"]
}
