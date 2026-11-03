"""Domain models shared across layers; for now only the paging result of a query."""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PageResult[T]:
    """One slice of items plus the total number of matching items."""

    items: Sequence[T]
    total: int
