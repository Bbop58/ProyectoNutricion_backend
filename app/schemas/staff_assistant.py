from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Meal = Literal['', 'Desayuno', 'Almuerzo', 'Cena', 'Merienda', 'Snack']


class AssistantIntent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['recommend', 'patients', 'help']
    patient_name: str = Field(default='', max_length=80)
    meal: Meal = ''


class AssistantQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message: str = Field(min_length=1, max_length=800)
    patient_id: str | None = Field(default=None, min_length=1, max_length=36)
    intent: Literal['recommend', 'patients'] | None = None
    meal: Meal = ''
    exclude_recipe_ids: list[Annotated[str, Field(min_length=1, max_length=36)]] = Field(default_factory=list, max_length=32)

    @field_validator('message')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('Escribe tu consulta.')
        return value.strip()


class AssistantConfirm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    proposal_token: str = Field(min_length=1, max_length=4096)
