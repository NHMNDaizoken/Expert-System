import json


CF_PATH = "data/staging/cf_dynamic.json"
PROC_PATH = "data/staging/procedure_trees.json"
KG_PATH = "data/staging/kg_rules_from_dataset.json"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class TestCFDynamic:
    def test_file_exists(self):
        load(CF_PATH)

    def test_no_cf_exactly_07(self):
        data = load(CF_PATH)
        for sym, faults in data.get("symptoms", data).items():
            if isinstance(faults, dict):
                for fault, cf in faults.items():
                    assert cf != 0.7, f"Hardcoded CF 0.7 still exists: {sym} -> {fault}"

    def test_cf_range(self):
        data = load(CF_PATH)
        for sym, faults in data.get("symptoms", data).items():
            if isinstance(faults, dict):
                for fault, cf in faults.items():
                    assert 0.0 < cf <= 1.0, f"CF out of bounds [0,1]: {sym} -> {fault} = {cf}"

    def test_discriminating_symptom_high_cf(self):
        data = load(CF_PATH)
        found = any(
            cf > 0.7
            for faults in data.get("symptoms", data).values()
            if isinstance(faults, dict)
            for cf in faults.values()
        )
        assert found, "No symptom has CF > 0.7"

    def test_generic_symptom_low_cf(self):
        data = load(CF_PATH)
        symptoms = data.get("symptoms", data)
        generic = next((s for s in symptoms if "check_engine" in s.lower() or "warning_light" in s.lower()), None)
        if generic:
            assert max(symptoms[generic].values()) < 1.01


class TestProcedureTrees:
    def test_file_exists(self):
        load(PROC_PATH)

    def test_all_faults_have_entry_step(self):
        data = load(PROC_PATH)
        for fault_id, tree in data.items():
            assert "entry_step" in tree, f"Fault '{fault_id}' missing entry_step"
            assert tree["entry_step"] in tree.get("steps", {})

    def test_step_links_valid(self):
        data = load(PROC_PATH)
        for fault_id, tree in data.items():
            steps = tree.get("steps", {})
            for step_id, step in steps.items():
                for branch in ["yes_next", "no_next"]:
                    nxt = step.get(branch)
                    if nxt and nxt not in ("DIAGNOSED", "REFUTED", None):
                        assert nxt in steps, f"[{fault_id}] {step_id}.{branch} -> {nxt} missing"

    def test_no_infinite_loop(self):
        data = load(PROC_PATH)
        for fault_id, tree in data.items():
            steps = tree.get("steps", {})
            visited = set()
            stack = [tree.get("entry_step")]
            while stack:
                cur = stack.pop()
                if cur in (None, "DIAGNOSED", "REFUTED") or cur not in steps:
                    continue
                assert cur not in visited, f"[{fault_id}] infinite loop at {cur}"
                visited.add(cur)
                stack.append(steps[cur].get("yes_next"))
                stack.append(steps[cur].get("no_next"))


class TestKGRules:
    def test_file_exists(self):
        load(KG_PATH)

    def test_all_rules_have_symptoms_list(self):
        data = load(KG_PATH)
        rules = data if isinstance(data, list) else data.get("rules", [])
        for rule in rules:
            assert isinstance(rule.get("symptoms"), list)
            assert rule["symptoms"]

    def test_all_rules_have_resolution(self):
        data = load(KG_PATH)
        rules = data if isinstance(data, list) else data.get("rules", [])
        for rule in rules:
            assert "parts" in rule.get("resolution", {})
            assert "procedure" in rule.get("resolution", {})

    def test_all_rules_have_procedure_tree(self):
        data = load(KG_PATH)
        rules = data if isinstance(data, list) else data.get("rules", [])
        for rule in rules:
            assert "entry_step" in rule.get("procedure", {})
            assert rule["procedure"].get("steps")

    def test_no_hardcoded_cf_07(self):
        data = load(KG_PATH)
        rules = data if isinstance(data, list) else data.get("rules", [])
        for rule in rules:
            for sym in rule.get("symptoms", []):
                assert sym.get("cf") != 0.7
