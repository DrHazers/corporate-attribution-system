from pydantic import BaseModel, Field


class ApiErrorResponse(BaseModel):
    detail: str = Field(
        description="Human-readable error detail for request validation or resource lookup failures."
    )
