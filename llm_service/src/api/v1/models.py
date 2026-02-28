from pydantic import BaseModel


class GenerateRequest(BaseModel):
    context: str = ""
    query: str
