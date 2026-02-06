from __future__ import annotations

"""
Future connectors stub.

This project is designed around the connector adapter interface in
`trading_bot.connectors.base.BrokerConnector`. To add other broker types:

- CryptoExchangeConnector (ccxt)
- StockBrokerConnector (Alpaca/IBKR/etc.)

Implement the interface and ensure:
  - candles -> pandas DataFrame with UTC-aware timestamps
  - positions/deals models filled consistently
  - account_info.trade_mode populated to enforce paper-trading safety gates

TODO: add connectors when required.
"""

from trading_bot.connectors.base import BrokerConnector


class CryptoExchangeConnector(BrokerConnector):  # pragma: no cover
    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError("Not implemented. Use MT5Connector for now.")


class StockBrokerConnector(BrokerConnector):  # pragma: no cover
    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError("Not implemented. Use MT5Connector for now.")

