from abc import ABC, abstractmethod
from typing import Any, Optional, Type, TypeVar
from pydantic import BaseModel
from util.settings import settings

import logging

# Set the underlying libraries to DEBUG
logging.getLogger("httpx").setLevel(logging.getLevelNamesMapping().get(settings.log_level))  # type: ignore
logging.getLogger("postgrest").setLevel(logging.getLevelNamesMapping().get(settings.log_level))  # type: ignore

# LOGGER = LoggerFactory.create_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class NotNull:
    """Sentinel value for 'IS NOT NULL' conditions in queries."""
    def __repr__(self) -> str:
        return "NOT_NULL"

NOT_NULL = NotNull()
"""Use as a condition value to filter for non-null fields.
Example: select_many("table", Model, {"field": NOT_NULL})
"""


class DatabaseManager(ABC):
    @abstractmethod
    def select_one(self, table:str, result_type: Type[T], condition: dict[str, Any], selection: str="*") -> Optional[T]:
        pass

    @abstractmethod
    def select_many(self, table:str, result_type: Type[T], condition: dict[str, Any], sort_by: Optional[str] = None, sort_direction: str = "asc", start: Optional[int] = None, end: Optional[int] = None, selection: str="*") -> tuple[list[T], int]:
        pass

    @abstractmethod
    def insert(self, table:str, data: dict[str, Any], result_type: Type[T]) -> T:
        pass

    @abstractmethod
    def upsert(self, table: str, data: dict[str, Any], result_type: Type[T], on_conflict: str) -> T:
        pass

    @abstractmethod
    def update(self, table:str, record_id: Any, data: dict[str, Any], result_type: Type[T]) -> T:
        pass

    @abstractmethod
    def delete(self, table:str, record_id: Any) -> bool:
        pass

    @abstractmethod
    def exists(self, table:str, field: str, value: Any) -> bool:
        pass
