from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, field_validator


class MeasurementIn(BaseModel):
    weight_kg: float = Field(gt=0, le=500, allow_inf_nan=False)
    height_cm: float = Field(ge=30, le=260, allow_inf_nan=False)
    measured_at: AwareDatetime | None = None


class AssessmentIn(BaseModel):
    start_date: date
    end_date: date


class NutritionValues(BaseModel):
    model_config = ConfigDict(extra='forbid')
    meals_per_day: int = Field(4, ge=1, le=12)
    inactivity_days: int = Field(7, ge=1, le=90)
    water_liters: float = Field(2, gt=0, le=10, allow_inf_nan=False)
    sleep_hours: float = Field(7, ge=1, le=24, allow_inf_nan=False)


class NutritionConfigIn(BaseModel):
    values: NutritionValues
    reason: str = Field(min_length=3, max_length=500)

    @field_validator('reason')
    @classmethod
    def reason_not_blank(cls, value):
        if len(value.strip()) < 3: raise ValueError('Indica el motivo del cambio.')
        return value.strip()


class ReviewIn(BaseModel):
    decision: Literal['CORRECTED', 'APPROVED', 'REJECTED']
    reason: str = Field(min_length=3, max_length=2000)
    clinical_notes: str | None = Field(None, max_length=5000)

    @field_validator('reason')
    @classmethod
    def reason_not_blank(cls, value):
        if len(value.strip()) < 3: raise ValueError('Indica el motivo de la decisión.')
        return value.strip()


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    @field_validator('content')
    @classmethod
    def not_blank(cls, value):
        if not value.strip(): raise ValueError('Escribe un mensaje.')
        return value.strip()


class ImportIn(BaseModel):
    csv_content: str = Field(min_length=1, max_length=1_000_000)
    branch_id: str | None = None
