from typing import Optional
from src.expert_system.inference.engine import ExpertSystemEngine

class Container:
    _engine: Optional[ExpertSystemEngine] = None

    @classmethod
    def get_engine(cls) -> ExpertSystemEngine:
        if cls._engine is None:
            cls._engine = ExpertSystemEngine.from_staging()
        return cls._engine

    @classmethod
    def reset_engine(cls):
        cls._engine = None

container = Container()
