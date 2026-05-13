import time
import json
from src.expert_system.knowledge.loader import KnowledgeBase
from src.expert_system.inference.engine import ExpertSystemEngine
from src.expert_system.inference.fuzzy import SymptomMatcher
from src.expert_system.inference.certainty import rank_faults
from src.expert_system.inference.question import select_information_gain_question
from src.expert_system.runtime.state import WorkingMemory

def benchmark():
    metrics = {}

    # 1. KB load time
    start = time.perf_counter()
    kb = KnowledgeBase.from_staging()
    metrics["kb_load_time_ms"] = (time.perf_counter() - start) * 1000

    # 2. Engine initialization time
    start = time.perf_counter()
    engine = ExpertSystemEngine(kb=kb)
    metrics["engine_init_time_ms"] = (time.perf_counter() - start) * 1000

    test_input = "xe không nổ máy và có khói đen"

    # 3. Fuzzy match latency
    start = time.perf_counter()
    matched = engine.matcher.match(test_input)
    metrics["fuzzy_match_latency_ms"] = (time.perf_counter() - start) * 1000

    # Setup for next steps
    memory = WorkingMemory.from_input([m["symptom_id"] for m in matched], None, None)
    memory.primary_symptom = engine._select_primary_symptom(memory.confirmed_symptoms)
    memory.detected_systems = engine._detect_systems(memory.confirmed_symptoms)
    candidates = engine._candidate_rules(memory)

    # 4. Candidate ranking latency
    start = time.perf_counter()
    ranked = rank_faults(memory.confirmed_symptoms, memory.rejected_symptoms, candidates, kb)
    metrics["candidate_ranking_latency_ms"] = (time.perf_counter() - start) * 1000

    # 5. Question selection latency
    start = time.perf_counter()
    if ranked:
        select_information_gain_question(memory, ranked, kb, 8)
    metrics["question_selection_latency_ms"] = (time.perf_counter() - start) * 1000

    # 6. Full diagnosis latency
    start = time.perf_counter()
    engine.diagnose(test_input)
    metrics["full_diagnosis_latency_ms"] = (time.perf_counter() - start) * 1000

    print("========================================")
    print(" ENGINE PERFORMANCE BENCHMARK ")
    print("========================================")
    for key, value in metrics.items():
        print(f"{key.ljust(35)}: {value:.2f} ms")
    
    with open("benchmark_report.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

if __name__ == "__main__":
    benchmark()
