"""Persistent storage for Decibench runs and production call traces."""

from decibench.store.sqlite import RunStore, default_store_path


def get_store() -> RunStore:
    """Return a RunStore instance using the default path."""
    return RunStore()


__all__ = ["RunStore", "default_store_path", "get_store"]
