from src.expert_system.engine import ExpertSystemEngine

def combine_cf(cf_old: float, cf_new: float) -> float:
    """Backward compatibility wrapper for combine_cf."""
    return ExpertSystemEngine._combine_cf(cf_old, cf_new)

__all__ = ["combine_cf"]
