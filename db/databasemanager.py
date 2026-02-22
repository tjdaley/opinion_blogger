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

class DatabaseManager(ABC):
    @abstractmethod
    def select_one(self, table:str, result_type: Type[T], condition: dict[str, Any]) -> Optional[T]:
        pass

    @abstractmethod
    def select_many(self, table:str, result_type: Type[T], condition: dict[str, Any], sort_by: Optional[str] = None, sort_direction: str = "asc", start: Optional[int] = None, end: Optional[int] = None) -> tuple[list[T], int]:
        pass

    @abstractmethod
    def insert(self, table:str, data: dict[str, Any], result_type: Type[T]) -> T:
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
