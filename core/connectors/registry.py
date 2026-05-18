import importlib
import inspect
import logging
import pkgutil
from typing import Dict, Type

import core.connectors
from core.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

class ConnectorRegistry:
    _registry: Dict[str, Type[BaseConnector]] = {}

    @classmethod
    def register(cls, connector_cls: Type[BaseConnector]):
        instance = connector_cls()
        cls._registry[instance.name] = connector_cls

    @classmethod
    def _autodiscover_connectors(cls) -> None:
        """
        Best-effort dynamic connector discovery.
        Useful when a worker is running a partial/stale import state.
        """
        for module_info in pkgutil.iter_modules(core.connectors.__path__):
            module_name = module_info.name
            if not module_name.startswith("conn_"):
                continue

            fq_module = f"core.connectors.{module_name}"
            try:
                module = importlib.import_module(fq_module)
            except Exception as exc:
                logger.warning("Connector autodiscovery failed importing %s: %s", fq_module, exc)
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if not issubclass(obj, BaseConnector) or obj is BaseConnector:
                    continue
                if obj.__module__ != module.__name__:
                    continue
                try:
                    cls.register(obj)
                except Exception as exc:
                    logger.warning(
                        "Connector autodiscovery failed registering %s.%s: %s",
                        module.__name__,
                        obj.__name__,
                        exc,
                    )
    
    @classmethod
    def get_connector(cls, name: str) -> BaseConnector:
        connector_cls = cls._registry.get(name)
        if not connector_cls:
            cls._autodiscover_connectors()
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
from core.connectors.conn_morgan_stanley import MorganStanleyConnector

ConnectorRegistry.register(JPMorganConnector)
ConnectorRegistry.register(JefferiesConnector)
ConnectorRegistry.register(ItauOnshoreConnector)
ConnectorRegistry.register(BtgUsConnector)
ConnectorRegistry.register(BtgCaymanConnector)
ConnectorRegistry.register(BtgMfoConnector)
ConnectorRegistry.register(MorganStanleyConnector)
