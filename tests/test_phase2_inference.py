from src.legacy.kg_inference import check_diagnosed, load_cf_map, rank_faults
from src.legacy.next_question import get_next_from_tree, select_by_information_gain


SAMPLE_RULES = [
    {
        "fault_id": "fault_a",
        "fault_name": "Fault A",
        "symptoms": [{"symptom_id": "sym_x", "cf": 0.9}, {"symptom_id": "sym_y", "cf": 0.2}],
        "procedure": {
            "entry_step": "a_s1",
            "steps": {
                "a_s1": {"id": "a_s1", "question": "Confirm A?", "yes_next": "DIAGNOSED", "no_next": "a_s2"},
                "a_s2": {"id": "a_s2", "question": "Check secondary A?", "yes_next": "DIAGNOSED", "no_next": "REFUTED"},
            },
        },
    },
    {
        "fault_id": "fault_b",
        "fault_name": "Fault B",
        "symptoms": [{"symptom_id": "sym_x", "cf": 0.1}, {"symptom_id": "sym_y", "cf": 0.8}],
        "procedure": {
            "entry_step": "b_s1",
            "steps": {
                "b_s1": {"id": "b_s1", "question": "Confirm B?", "yes_next": "DIAGNOSED", "no_next": "REFUTED"},
            },
        },
    },
]


def test_load_cf_map():
    cf_map = load_cf_map(SAMPLE_RULES)
    assert cf_map["sym_x"]["fault_a"] == 0.9
    assert cf_map["sym_y"]["fault_b"] == 0.8


def test_rank_faults_uses_dynamic_cf():
    ranked = rank_faults(["sym_x"], [], load_cf_map(SAMPLE_RULES), SAMPLE_RULES)
    assert ranked[0]["fault_id"] == "fault_a"
    assert ranked[0]["cf_breakdown"][0]["cf"] == 0.9


def test_not_diagnosed_when_scores_close():
    assert not check_diagnosed([{"score": 0.55}, {"score": 0.45}])


def test_diagnosed_when_top_has_gap():
    assert check_diagnosed([
        {"score": 0.85, "matched_rules": [{"symptom_id": "sym_x"}, {"symptom_id": "sym_y"}], "question_count": 1},
        {"score": 0.10},
    ])


def test_information_gain_selects_unasked_symptom():
    ranked = [{"fault_id": "fault_a", "score": 0.6}, {"fault_id": "fault_b", "score": 0.4}]
    result = select_by_information_gain(ranked, {"sym_x"}, ["sym_x", "sym_y"], load_cf_map(SAMPLE_RULES))
    assert result["symptom_id"] == "sym_y"
    assert result["information_gain"] > 0


def test_procedure_tree_follow():
    procedure = SAMPLE_RULES[0]["procedure"]
    assert get_next_from_tree("a_s1", True, procedure)["terminal"] == "DIAGNOSED"
    result = get_next_from_tree("a_s1", False, procedure)
    assert result["step_id"] == "a_s2"
    assert result["terminal"] is None


def test_procedure_tree_no_loop_terminal():
    procedure = SAMPLE_RULES[1]["procedure"]
    assert get_next_from_tree("b_s1", True, procedure)["terminal"] == "DIAGNOSED"
    assert get_next_from_tree("b_s1", False, procedure)["terminal"] == "REFUTED"
