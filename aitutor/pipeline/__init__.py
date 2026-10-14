"""Course construction pipeline: ingest → source → build → provenance → store → lecture."""

from aitutor.pipeline.builder import BuildRequest, build_prompt_pack
from aitutor.pipeline.course_store import (
    StoredCourse,
    extract_course_json,
    list_built,
    load_course,
    save_course,
    save_from_llm_text,
)
from aitutor.pipeline.ingest import IngestedMaterial, ingest_path, ingest_text
from aitutor.pipeline.provenance import attach_provenance, cite_record, sha256_file
from aitutor.pipeline.sources import SourceRecord, SourceRegistry

__all__ = [
    "BuildRequest",
    "IngestedMaterial",
    "SourceRecord",
    "SourceRegistry",
    "StoredCourse",
    "attach_provenance",
    "build_prompt_pack",
    "cite_record",
    "extract_course_json",
    "ingest_path",
    "ingest_text",
    "list_built",
    "load_course",
    "save_course",
    "save_from_llm_text",
    "sha256_file",
]