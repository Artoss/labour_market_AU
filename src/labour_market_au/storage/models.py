"""
Pydantic models for database entities.
"""

from __future__ import annotations

from pydantic import BaseModel


class SALMRecord(BaseModel):
    """A single SALM observation (long format)."""
    geo_code: str
    geo_name: str
    geo_level: str  # sa2 | lga
    measure: str  # unemployment_rate | unemployed_persons | labour_force
    period: str  # e.g. "Jun 2024"
    value: float | None = None
    smoothed: bool = True


class IVIRecord(BaseModel):
    """A single IVI observation (long format)."""
    anzsco_code: str
    anzsco_title: str = ""
    state: str = ""
    skill_level: str = ""
    period: str  # e.g. "Jan 2024"
    value: float | None = None
    index_type: str = "level"  # level | index


class ProjectionsRecord(BaseModel):
    """A single Employment Projections observation."""
    anzsco_code: str
    occupation_name: str = ""
    industry_code: str = ""
    industry_name: str = ""
    state: str = ""
    measure: str = ""  # employment_level | growth_rate | growth_number
    base_year: int = 0
    projection_year: int = 0
    value: float | None = None


class ScrapeFile(BaseModel):
    """Tracking record for a downloaded file."""
    site: str
    dataset: str
    filename: str
    url: str
    file_hash: str = ""
    file_size_bytes: int = 0
    records_loaded: int = 0
    skipped: bool = False
