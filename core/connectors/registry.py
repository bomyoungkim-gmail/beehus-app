from core.connectors.base import BaseConnector
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

# Register connectors
from core.connectors.conn_jpmorgan import JPMorganConnector
from core.connectors.conn_itau_onshore import ItauOnshoreConnector
from core.connectors.conn_btg_us import BtgUsConnector
from core.connectors.conn_btg_cayman import BtgCaymanConnector
from core.connectors.conn_jefferies import JefferiesConnector
from core.connectors.conn_btg_mfo import BtgMfoConnector

ConnectorRegistry.register(JPMorganConnector)
ConnectorRegistry.register(JefferiesConnector)
ConnectorRegistry.register(ItauOnshoreConnector)
ConnectorRegistry.register(BtgUsConnector)
ConnectorRegistry.register(BtgCaymanConnector)
ConnectorRegistry.register(BtgMfoConnector)
