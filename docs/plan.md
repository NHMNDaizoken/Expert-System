# Expert System Cleanup Plan

## Goal checklist

- [ ] User questions are symptom-based and understandable to normal vehicle owners.
- [ ] Technician diagnostic and repair steps appear only after a diagnosis result.
- [ ] Repair, diagnosis, UI, and graph labels are localized consistently in Vietnamese.
- [ ] Graph relationships use clean Vietnamese labels instead of raw relation codes.
- [ ] Diagnostic flows cannot loop forever.
- [ ] The UI is polished enough for review and project defense.
- [ ] Documentation clearly explains the expert-system structure.
- [ ] Manual review and tests cover questions, localization, graph labels, loops, and defense readiness.

## Phase 1 Audit Current Flow

- [ ] Find where procedure trees are generated.
- [ ] Find where user questions are created and displayed.
- [ ] Find where technician diagnosis and repair steps are stored.
- [ ] Find graph node and edge label formatting logic.
- [ ] Find any runtime-generated labels such as `Diagnosis for` and `Repair for`.
- [ ] Identify any places raw English labels can bypass the translation pipeline.

## Phase 2 Fix User Questions

- [ ] Generate user-facing questions from symptoms, not technician procedures.
- [ ] Ensure each question maps to a symptom ID.
- [ ] Remove questions that ask users to measure, inspect, test, or use tools.
- [ ] Review fallback question templates for natural Vietnamese wording.
- [ ] Confirm normal users can answer the questions from observable vehicle behavior.

## Phase 3 Separate Technician Procedures

- [ ] Keep technician diagnosis steps out of the question flow.
- [ ] Show inspection, measurement, and repair steps only after a diagnosis result.
- [ ] Separate symptom facts, rules, procedure trees, and technician steps in generated data.
- [ ] Make result screens clearly distinguish diagnosis, explanation, and recommended technician actions.

## Phase 4 Fix Vietnamese Labels

- [ ] Localize repair and diagnosis labels such as `Diagnosis for Diesel Glow Plug`.
- [ ] Localize generated action labels with Vietnamese verbs such as `Kiểm tra`, `Thay`, `Vệ sinh`, and `Điều chỉnh`.
- [ ] Ensure key terms such as diesel glow plug, wheel bearing, misfire, symptoms, and approved states are Vietnamese in user-facing views.
- [ ] Check hardcoded UI strings, generated labels, and data-driven labels for mixed English/Vietnamese output.

## Phase 5 Fix Graph Relations

- [ ] Replace raw relation codes such as `HAS_SYMPTOM`, `FIXED_BY`, and `AFFECTS` with Vietnamese display labels.
- [ ] Remove confidence values from graph edge labels.
- [ ] Show confidence and metadata only in detail panels where needed.
- [ ] Keep graph edges readable and focused on relationship names.
- [ ] Avoid awkward labels such as `Được xử lý bởi` when a clearer repair relationship label is needed.

## Phase 6 Prevent Loops

- [ ] Track visited question IDs during diagnostic traversal.
- [ ] Stop traversal when a repeated question is detected.
- [ ] Add a maximum question depth guard.
- [ ] Validate procedure trees for cycles and missing transition targets.
- [ ] Provide a safe fallback result when a flow is incomplete or invalid.

## Phase 7 UI Polish

- [ ] Use consistent card padding, spacing, border radius, and badge sizing.
- [ ] Prefer top-aligned content for cards, graph nodes, and detail panels.
- [ ] Reduce graph visual noise.
- [ ] Keep relationship labels short and readable.
- [ ] Ensure result details, reasoning, and technician steps are easy to scan.
- [ ] Manually review main screens for mixed language, alignment issues, and clutter.

## Phase 8 Defense Documentation

- [ ] Document where the knowledge base lives.
- [ ] Document where the rule base lives.
- [ ] Document where the inference engine lives.
- [ ] Explain how user answers map to symptoms and rules.
- [ ] Explain why technician procedures are separated from user questions.
- [ ] Explain that the graph is for visualization and explanation, not the main inference engine.
- [ ] Explain whether Neo4j is optional and how JSON data supports the expert system.

## Test Checklist

- [ ] No user-facing question is generated from technician diagnosis or repair steps.
- [ ] No user question requires tools, measurements, or mechanical inspection.
- [ ] Repair and diagnosis labels are localized in Vietnamese.
- [ ] Graph edges show Vietnamese relation names only.
- [ ] Graph edges do not show raw relation codes or confidence numbers.
- [ ] Procedure trees have unique question IDs.
- [ ] `yes` and `no` transitions resolve to valid questions or results.
- [ ] Cycles are detected or prevented.
- [ ] Maximum question depth is enforced.
- [ ] Inference tests rank expected faults from selected symptoms.
- [ ] Result screens show technician steps only after diagnosis.
- [ ] Manual review covers several complete diagnostic flows.
- [ ] Defense review can answer knowledge base, rule base, inference engine, procedure tree, graph purpose, and Neo4j questions.

## Assumptions

- [ ] The source dataset may contain English technical terms and technician procedures.
- [ ] Translation files alone are not enough; runtime label formatting is also required.
- [ ] User-facing questions should be based on symptoms and observable vehicle behavior.
- [ ] Technician procedures remain useful, but only as post-diagnosis guidance.
- [ ] The knowledge graph supports explanation and visualization, while rules and inference produce diagnoses.
