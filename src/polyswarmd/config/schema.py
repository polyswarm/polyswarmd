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
                "directory": {"type": "string"},
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

CHAIN_CONFIG_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "chain.json",
    "type": "object",
    "properties": {
        "nectar_token_address": {"type": "string"},
        "arbiter_staking_address": {"type": "string"},
        "erc20_relay_address": {"type": "string"},
        "offer_registry_address": {"type": "string"},
        "bounty_registry_address": {"type": "string"},
        "eth_uri": {"type": "string"},
        "chain_id": {"type": "integer"},
        "free": {"type": "boolean"},
        "contracts": {
            "type": "object",
            "additionalItems": True
        }
    },
    "required": ["nectar_token_address", "arbiter_staking_address", "erc20_relay_address", "offer_registry_address",
                 "bounty_registry_address", "eth_uri", "chain_id", "free", "contracts"],
}
