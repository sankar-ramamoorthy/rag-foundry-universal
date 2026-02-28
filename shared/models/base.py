from sqlalchemy import MetaData
from sqlalchemy.orm import declarative_base

metadata = MetaData(schema="ingestion_service")
Base = declarative_base(metadata=metadata)