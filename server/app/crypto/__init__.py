"""Crypto Intelligence domain — read-only market research foundation."""

__all__ = ["crypto_router"]


def __getattr__(name: str):
    if name == "crypto_router":
        from .router import router as crypto_router
        return crypto_router
    raise AttributeError(name)
