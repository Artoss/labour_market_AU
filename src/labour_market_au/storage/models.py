"""
Pydantic models for database entities.
"""

from __future__ import annotations

from pydantic import BaseModel


class SALMRecord(BaseModel):
    """A single SALM observation (long format)."""
    geo_code: str
    geo_name: str
    geo_type: str  # sa2 | lga
    measure: str  # unemployment_rate | unemployed_persons | labour_force
    period: str  # e.g. "Jun 2024"
    value: float | None = None
    smoothed: bool = True


class IVIRecord(BaseModel):
    """A single IVI observation (long format)."""
    anzsco_code: str
    anzsco_title: str = ""
    geo_area: str = ""
    geo_type: str = ""
    skill_level: str = ""
    period: str  # e.g. "Jan 2024"
    value: float | None = None
    index_type: str = "level"  # level | index
    file_type: str = ""


class ProjectionsRecord(BaseModel):
    """A single Employment Projections observation."""
    dimension_type: str = ""
    anzsco_code: str
    occupation_name: str = ""
    industry_code: str = ""
    industry_name: str = ""
    geo_area: str = ""
    geo_type: str = ""
    measure: str = ""  # employment_level | growth_rate | growth_number
    base_year: int = 0
    projection_year: int = 0
    value: float | None = None


class TNVRecord(BaseModel):
    """A single Total New Vacancies observation."""
    dimension_type: str  # region | occupation
    level: int
    anzsco_code: str = ""
    anzsco_title: str = ""
    geo_type: str = ""
    geo_area: str = ""
    parent_geo: str = ""
    period: str
    value: float | None = None


class RLMIRecord(BaseModel):
    """A single RLMI observation."""
    data_source: str
    sa4_code: str = ""
    sa4_name: str = ""
    geo_type: str = ""
    measure: str
    period: str
    value: float | None = None
    rating_value: int | None = None
    rating_text: str = ""


class LFTRecord(BaseModel):
    """A single Labour Force Trending observation."""
    file_type: str
    level: int
    code: str
    title: str = ""
    geo_area: str = ""
    geo_type: str = ""
    parent_code: str = ""
    period: str
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
