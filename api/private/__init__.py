"""
Private API Module - À compléter avec vos credentials
"""

from .polymarket_private import PolymarketPrivateClient, PolymarketCredentials
from .credentials import CredentialsManager, APICredentials

__all__ = [
    "PolymarketPrivateClient",
    "PolymarketCredentials",
    "CredentialsManager",
    "APICredentials",
]
