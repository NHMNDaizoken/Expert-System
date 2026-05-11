from src.expert_system.engine import ExpertSystemEngine, load_cf_map, rank_faults
from src.expert_system.knowledge_base import KnowledgeBase
from src.expert_system.procedure import ProcedureRunner as ProcedureReasoner
from src.expert_system.matcher import SymptomMatcher
from src.expert_system.schemas import ExpertSystemValidator
from src.expert_system.engine import WorkingMemory


ALIASES = {
    "SYM_CLICK": {
        "name": "click",
        "display_name": "Clicking sound",
        "aliases": ["clicking noise"],
    },
    "SYM_DIM": {
        "name": "dim_lights",
        "display_name": "Dim lights",
        "aliases": ["dim headlights"],
    },
}

RULES = [
    {
        "fault_id": "FLT_BATTERY",
        "fault_name": "weak_battery",
        "display_name": "Weak Battery",
        "system_id": "SYS_ELECTRICAL",
        "symptom": "SYM_CLICK",
        "symptoms": [
            {"symptom_id": "SYM_CLICK", "cf": 0.6, "priority": 1},
            {"symptom_id": "SYM_DIM", "cf": 0.9, "priority": 2, "deterministic": True},
        ],
        "procedure": {
            "entry_step": "bat_s1",
            "steps": {
                "bat_s1": {"id": "bat_s1", "question": "Measure battery voltage?", "yes_next": "DIAGNOSED", "no_next": "REFUTED"}
            },
        },
        "resolution": {"procedure": "Charge or replace battery."},
    },
    {
        "fault_id": "FLT_STARTER",
        "fault_name": "starter",
        "display_name": "Starter",
        "system_id": "SYS_ELECTRICAL",
        "symptom": "SYM_CLICK",
        "symptoms": [{"symptom_id": "SYM_CLICK", "cf": 0.7, "priority": 1}],
        "resolution": {"procedure": "Inspect starter."},
    },
]


def kb():
    return KnowledgeBase.from_data(symptom_aliases=ALIASES, rules=RULES)


def test_symptom_matcher_alias_and_unknown():
    matcher = SymptomMatcher(ALIASES)

    assert matcher.match("there is a clicking noise")[0]["symptom_id"] == "SYM_CLICK"
    assert matcher.match("rear window squeaks loudly") == []


def test_cf_ranking_confidence_and_rejected_context():
    cf_map = load_cf_map(RULES)

    confirmed = rank_faults(["SYM_CLICK", "SYM_DIM"], [], cf_map, RULES)
    rejected = rank_faults(["SYM_CLICK"], ["SYM_DIM"], cf_map, RULES)

    assert confirmed[0]["fault_id"] == "FLT_BATTERY"
    assert confirmed[0]["final_cf"] > confirmed[1]["final_cf"]
    assert rejected[0]["fault_id"] == "FLT_STARTER"
    assert confirmed[0]["score_breakdown"]["note"].endswith("not Bayesian probability.")


def test_procedure_reasoner_terminal_and_next_step():
    reasoner = ProcedureReasoner()
    procedure = RULES[0]["procedure"]

    assert reasoner.entry_step(procedure)["step_id"] == "bat_s1"
    assert reasoner.get_next_from_tree("bat_s1", True, procedure)["terminal"] == "DIAGNOSED"
    assert reasoner.get_next_from_tree("bat_s1", False, procedure)["terminal"] == "REFUTED"


def test_working_memory_updates_confirmed_and_rejected_symptoms():
    memory = WorkingMemory.from_input(["SYM_CLICK"], rejected_symptoms=["SYM_DIM"])

    memory.confirm("SYM_DIM")
    memory.reject("SYM_CLICK")

    assert memory.confirmed_symptoms == ["SYM_DIM"]
    assert memory.rejected_symptoms == ["SYM_CLICK"]


def test_engine_need_more_info_uses_current_hypotheses_not_results():
    engine = ExpertSystemEngine(kb())

    response = engine.diagnose("clicking noise", top_k=2)

    assert response["status"] == "need_more_info"
    assert response["results"] == []
    assert response["current_hypotheses"]
    assert len(response["candidate_faults"]) == 2
    assert response["detected_systems"] == ["SYS_ELECTRICAL"]
    assert response["primary_symptom"] == "SYM_CLICK"


def test_engine_diagnosed_uses_results_and_resolution():
    engine = ExpertSystemEngine(kb())

    response = engine.diagnose("clicking noise and dim headlights", top_k=2)

    assert response["status"] == "need_more_info"
    assert response["results"] == []
    assert response["next_question"]["mode"] == "procedure_tree"
    assert response["procedure_terminal"] is None


def test_single_primary_symptom_with_100_cf_is_not_final_without_deterministic_rule():
    rules = [
        {
            "fault_id": "FLT_ABS_MODULE",
            "fault_name": "abs_module",
            "display_name": "ABS Control Module",
            "system_id": "SYS_ABS",
            "symptom": "SYM_ABS",
            "candidate_fault_ids": ["FLT_ABS_MODULE", "FLT_ABS_SENSOR"],
            "symptoms": [{"symptom_id": "SYM_ABS", "cf": 1.0, "priority": 1}],
        },
        {
            "fault_id": "FLT_ABS_SENSOR",
            "fault_name": "abs_sensor",
            "display_name": "ABS Wheel Speed Sensor",
            "system_id": "SYS_ABS",
            "symptoms": [{"symptom_id": "SYM_SPEEDOMETER", "cf": 0.9, "priority": 2}],
        },
    ]
    aliases = {
        "SYM_ABS": {"display_name": "ABS warning light on", "aliases": ["ABS warning light on"]},
        "SYM_SPEEDOMETER": {"display_name": "Erratic speedometer", "aliases": ["erratic speedometer"]},
    }

    response = ExpertSystemEngine(KnowledgeBase.from_data(symptom_aliases=aliases, rules=rules)).diagnose(
        "ABS warning light on",
        top_k=2,
    )

    assert response["status"] == "need_more_info"
    assert not response["is_final"]
    assert response["results"] == []
    assert response["detected_systems"] == ["SYS_ABS"]
    assert {fault["fault_id"] for fault in response["candidate_faults"]} == {"FLT_ABS_MODULE", "FLT_ABS_SENSOR"}


def test_multi_step_procedure_leaf_can_diagnose_after_follow_up_answers():
    aliases = {"SYM_ABS": {"display_name": "ABS warning light on", "aliases": ["ABS warning light on"]}}
    rules = [
        {
            "fault_id": "FLT_ABS_MODULE",
            "fault_name": "abs_module",
            "display_name": "ABS Control Module",
            "system_id": "SYS_ABS",
            "symptom": "SYM_ABS",
            "symptoms": [{"symptom_id": "SYM_ABS", "cf": 1.0, "priority": 1}],
            "procedure": {
                "entry_step": "abs_s1",
                "steps": {
                    "abs_s1": {"id": "abs_s1", "question": "Check ABS fuse?", "yes_next": "abs_s2", "no_next": "REFUTED"},
                    "abs_s2": {"id": "abs_s2", "question": "Inspect wiring?", "yes_next": "DIAGNOSED", "no_next": "REFUTED"},
                },
            },
        }
    ]
    engine = ExpertSystemEngine(KnowledgeBase.from_data(symptom_aliases=aliases, rules=rules))

    first = engine.diagnose("ABS warning light on")
    second = engine.diagnose(
        "ABS warning light on",
        session={
            "confirmed_symptoms": ["SYM_ABS"],
            "current_step_id": first["next_question"]["step_id"],
            "step_history": [first["next_question"]["step_id"]],
            "last_answer": True,
        },
    )
    final = engine.diagnose(
        "ABS warning light on",
        session={
            "confirmed_symptoms": ["SYM_ABS"],
            "current_step_id": second["next_question"]["step_id"],
            "step_history": [first["next_question"]["step_id"], second["next_question"]["step_id"]],
            "last_answer": True,
        },
    )

    assert first["status"] == "need_more_info"
    assert second["status"] == "need_more_info"
    assert final["status"] == "diagnosed"
    assert final["is_final"]


def test_validator_reports_missing_cf_and_invalid_procedure_link():
    broken_rules = [
        {
            "fault_id": "FLT_BAD",
            "fault_name": "bad",
            "system_id": "SYS_ELECTRICAL",
            "symptoms": [{"symptom_id": "SYM_CLICK"}],
            "procedure": {
                "entry_step": "s1",
                "steps": {"s1": {"id": "s1", "question": "Check?", "yes_next": "missing", "no_next": "REFUTED"}},
            },
        }
    ]
    report = ExpertSystemValidator(KnowledgeBase.from_data(symptom_aliases=ALIASES, rules=broken_rules)).validate()

    assert not report.ok
    assert any("missing CF" in error for error in report.errors)
    assert any("invalid procedure link" in error for error in report.errors)
