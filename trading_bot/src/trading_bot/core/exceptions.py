from __future__ import annotations


class TradingBotError(Exception):
    """Base error for the trading bot."""


class ConfigError(TradingBotError):
    pass


class BrokerError(TradingBotError):
    pass


class BrokerDisconnectedError(BrokerError):
    pass


class RetryableBrokerError(BrokerError):
    pass


class RiskBlockedError(TradingBotError):
    pass


class PersistenceError(TradingBotError):
    pass

