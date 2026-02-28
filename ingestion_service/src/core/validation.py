# src/ingestion_service/core/validation.py


class MockValidator:
    """
    Simple validator for synchronous ingestion.
    Raises exception if input is empty or None.
    """

    def validate(self, text: str) -> None:
        if not text or not text.strip():
            raise ValueError("Input text cannot be empty")
