from pydantic import BaseModel, model_validator


class GenerateRequest(BaseModel):
    context: str = ""
    query: str
    evidence_passages: list[str] | None = None

    @model_validator(mode="after")
    def validate_passages(self):
        if self.evidence_passages is not None:
            if self.context != "\n\n".join(self.evidence_passages):
                raise ValueError("evidence passages must reconstruct context")
        return self
