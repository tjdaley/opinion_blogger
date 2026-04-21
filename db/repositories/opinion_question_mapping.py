"""
db/repositories/opinion_question_mapping.py - Repository for OpinionQuestionMapping model
"""
from typing import Any

from db.models.canonical_question import OpinionQuestionMappingInDB
from db_handler import DatabaseManager, BaseRepository


class OpinionQuestionMappingRepository(BaseRepository[OpinionQuestionMappingInDB]):
    def __init__(self, manager: DatabaseManager):
        super().__init__(manager, "opinion_question_mapping", OpinionQuestionMappingInDB)

    def upsert_mapping(self, data: dict[str, Any]) -> OpinionQuestionMappingInDB:
        """Insert or update a mapping, matching on (court_opinion_id, source_question_index)."""
        return self.upsert(data, on_conflict="court_opinion_id,source_question_index")

    def get_all_mapped_keys(self, page_size: int = 1000) -> set[tuple[int, int]]:
        """Return all (court_opinion_id, source_question_index) pairs that have mappings."""
        all_results: list[OpinionQuestionMappingInDB] = []
        offset = 0
        while True:
            batch, _ = self.select_many(
                condition={},
                start=offset,
                end=offset + page_size - 1,
            )
            all_results.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return {(m.court_opinion_id, m.source_question_index) for m in all_results}
