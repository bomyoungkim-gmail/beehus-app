from core.connectors.base import BaseConnector
from core.connectors.example import ExampleConnector
from typing import Dict, Type

class ConnectorRegistry:
    _registry: Dict[str, Type[BaseConnector]] = {}

    @classmethod
    def register(cls, connector_cls: Type[BaseConnector]):
        instance = connector_cls()
        cls._registry[instance.name] = connector_cls
    
    @classmethod
    def get_connector(cls, name: str) -> BaseConnector:
        connector_cls = cls._registry.get(name)
        if not connector_cls:
            raise ValueError(f"Connector '{name}' not found")
        return connector_cls()

from core.connectors.otp_example import OtpExampleConnector
# Register built-ins
ConnectorRegistry.register(ExampleConnector)
ConnectorRegistry.register(OtpExampleConnector)
