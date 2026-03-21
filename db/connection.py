"""
db/connection.py - Centralized database connection and repository singletons.

All modules should import their DB manager and repositories from here
instead of creating their own instances.
"""

from db.supabasemanager import SupabaseManager
from db.repositories.opinion_tracking import OpinionTrackingRepository
from db.repositories.court_opinion import OpinionRepository
from db.repositories.legal_subject import LegalSubjectRepository
from db.repositories.canonical_question_subject import CanonicalQuestionSubjectRepository
from db.repositories.canonical_question import CanonicalQuestionRepository
from db.repositories.opinion_question_mapping import OpinionQuestionMappingRepository

manager = SupabaseManager()
opinion_tracking_repo = OpinionTrackingRepository(manager)
court_opinion_repo = OpinionRepository(manager)
legal_subject_repo = LegalSubjectRepository(manager)
canonical_question_subject_repo = CanonicalQuestionSubjectRepository(manager)
canonical_question_repo = CanonicalQuestionRepository(manager)
opinion_question_mapping_repo = OpinionQuestionMappingRepository(manager)
