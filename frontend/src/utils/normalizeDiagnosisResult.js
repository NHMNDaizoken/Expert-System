// Normalizes various backend diagnosis responses into a common frontend model
export default function normalizeDiagnosisResult(raw) {
  if (!raw || typeof raw !== "object") return { type: "diagnosis", mode: "kg", results: [] };

  // Base model
  const model = {
    mode: raw.source || raw.status || "kg",
    type: "diagnosis",
    session_id: raw.session_id || raw.session || null,
    candidate_id: raw.candidate_id || raw.candidate?.candidate_id || null,
    root_symptom: { id: null, label: null, ...(raw.root_symptom || {}) },
    current_question: raw.current_question || raw.next_question || null,
    answer_options: raw.answer_options || raw.answers || [],
    selected_path: raw.selected_path || raw.selected_paths?.[0] || raw.answers || [],
    results: [],
    decision_tree: null,
    next_question: null,
    expert_review: { candidate_ready: false, payload: null },
    // keep legacy fields for backwards compatibility
    _raw: raw,
  };

  // Helper to convert a KG-style result into unified result
  function mapKgResult(r) {
    return {
      fault_id: r.fault_id || r.id || r.rule_id || null,
      fault_name: r.fault_label_vi || r.fault_label || r.fault_name || r.label || null,
      system: r.system || r.system_id || null,
      severity: r.severity || null,
      confidence: Number(r.final_cf ?? r.score ?? r.confidence ?? 0),
      symptoms: r.symptoms || r.normalized_symptoms || [],
      components: r.components || r.parts || r.repair_plan?.inspect_or_replace || [],
      causes: r.causes || r.possible_causes || [],
      diagnostic_steps: r.diagnostic_steps || r.repair_plan?.checks || r.repair_plan?.checks?.map((c) => c.action) || [],
      repair_steps: r.repair_steps || r.repair_plan?.inspect_or_replace || r.repair_plan?.repair_steps || r.repair_plan?.checks?.flatMap((c) => c.recommended_fix ? [c.recommended_fix] : []) || r.resolution?.procedure ? String(r.resolution.procedure).split(/\n|\./).map(s=>s.trim()).filter(Boolean) : [],
      safety_notes: r.safety_notes || r.when_to_stop || [],
      source: raw.source === "staging_files_kg" ? "knowledge_graph" : raw.source || "kg",
      resolution: r.resolution || null,
    };
  }

  const treeCandidate = raw.decision_tree || raw.llm_patch_suggestion;
  const isTerminalTreeResult = raw.type === "result" && raw.result_node;
  const isDecisionTreePayload =
    !isTerminalTreeResult &&
    (raw.type === "diagnostic_decision_tree" ||
      raw.type === "question" ||
      (Boolean(raw.decision_tree) &&
        treeCandidate &&
        treeCandidate.type === "diagnostic_decision_tree" &&
        (raw.type === "diagnostic_decision_tree" || raw.current_node)));

  // LLM decision tree flow (pre-approval temporary UI)
  if (isDecisionTreePayload) {
    const tree = treeCandidate;
    model.mode = raw.source === "llm_fallback" ? "llm_fallback" : raw.source || "llm_fallback";
    model.type = "diagnostic_decision_tree";
    model.decision_tree = tree;
    model.root_symptom = raw.root_symptom || tree?.root_symptom || model.root_symptom;
    model.selected_path = raw.selected_path || raw.selected_paths?.[0] || raw.answers || model.selected_path;

    // collect result leaves
    const nodes = (tree?.tree?.nodes || tree?.nodes || []).slice ? (tree?.tree?.nodes || tree?.nodes || []) : [];
    const leaves = nodes.filter((n) => n.type === "result").map((node) => {
      const fault = node.fault || node.result || {};
      return {
        fault_id: fault.fault_id || fault.id || null,
        fault_name: fault.fault_name || fault.fault_label_vi || fault.fault_label || null,
        system: fault.system || null,
        severity: fault.severity || null,
        confidence: Number(fault.confidence ?? fault.score ?? 0),
        symptoms: fault.symptoms || [],
        components: node.components || fault.components || [],
        causes: node.causes || fault.causes || [],
        diagnostic_steps: node.diagnostic_steps || fault.diagnostic_steps || [],
        repair_steps: node.repair_steps || fault.repair_steps || [],
        safety_notes: node.safety_notes || fault.safety_notes || [],
        source: "llm_fallback",
      };
    });

    model.results = leaves;
    // primary selected result is the leaf corresponding to selected_path last node if available
    if (model.selected_path && model.selected_path.length) {
      const last = model.selected_path[model.selected_path.length - 1];
      if (last?.node_id) {
        const sel = nodes.find((n) => n.node_id === last.node_id) || nodes.find((n) => n.node_id === last.next_node_id);
        if (sel && sel.type === "result") {
          model.results = [
            {
              fault_id: sel.fault?.fault_id || sel.fault?.id,
              fault_name: sel.fault?.fault_name || sel.fault?.fault_label_vi || sel.fault?.fault_label,
              system: sel.fault?.system,
              severity: sel.fault?.severity,
              confidence: Number(sel.fault?.confidence ?? 0),
              symptoms: sel.fault?.symptoms || [],
              components: sel.components || [],
              causes: sel.causes || [],
              diagnostic_steps: sel.diagnostic_steps || [],
              repair_steps: sel.repair_steps || [],
              safety_notes: sel.safety_notes || [],
              source: "llm_fallback",
            },
            ...leaves.filter((l) => l.fault_id !== (sel.fault?.fault_id || sel.fault?.id)),
          ];
        }
      }
    }

    model.expert_review = { candidate_ready: true, payload: { root_symptom: model.root_symptom, full_tree: tree, selected_path: model.selected_path, leaves: leaves, selected: model.results[0] } };
    // mirror legacy fields
    model.current_node = raw.current_node || raw.node || null;
    model.answers = raw.answers || raw.selected_path || [];
    const cq = model.current_node?.question || raw.current_node?.question;
    model.next_question =
      typeof cq === "string" && cq.trim() ? { question: cq.trim() } : model.current_node && model.current_node.question ? { question: model.current_node.question } : null;
    model.current_question = model.next_question;
    return model;
  }

  if (isTerminalTreeResult) {
    const sel = raw.result_node;
    const fault = sel.fault || {};
    model.mode = raw.source === "llm_fallback" ? "llm_fallback" : raw.source || "llm_fallback";
    model.type = "diagnosis";
    model.decision_tree = null;
    model.selected_path = raw.selected_path || [];
    model.results = [
      {
        fault_id: fault.fault_id || fault.id || null,
        fault_name: fault.fault_name || fault.fault_label_vi || fault.fault_label || null,
        system: fault.system || null,
        severity: fault.severity || null,
        confidence: Number(fault.confidence ?? fault.score ?? 0),
        symptoms: fault.symptoms || [],
        components: sel.components || fault.components || [],
        causes: sel.causes || fault.causes || [],
        diagnostic_steps: sel.diagnostic_steps || fault.diagnostic_steps || [],
        repair_steps: sel.repair_steps || fault.repair_steps || [],
        safety_notes: sel.safety_notes || fault.safety_notes || [],
        source: "llm_fallback",
      },
    ];
    model.expert_review = { candidate_ready: Boolean(raw.expert_review?.candidate_ready), payload: null };
    model.next_question = null;
    model.current_question = null;
    return model;
  }

  // KG / rule-based flow
  const sourceResults = raw.results || raw.matches || raw.diagnoses || [];
  model.mode = raw.source === "staging_files_kg" ? "knowledge_graph" : raw.source || "kg";
  model.root_symptom = raw.root_symptom || raw.symptom || model.root_symptom;

  model.results = (sourceResults || []).map((r) => mapKgResult(r));

  // If backend included repair_plan or resolution at top-level, enrich primary result
  const topResolution = raw.repair_plan || raw.repair_plan || raw.resolution || null;
  if (topResolution && model.results.length > 0) {
    const primary = model.results[0];
    primary.diagnostic_steps = primary.diagnostic_steps.length ? primary.diagnostic_steps : (topResolution.checks ? topResolution.checks.map((c) => c.action || c) : []);
    primary.repair_steps = primary.repair_steps.length ? primary.repair_steps : (topResolution.inspect_or_replace || topResolution.procedure || []);
    primary.components = primary.components.length ? primary.components : (topResolution.inspect_or_replace || topResolution.parts || []);
    primary.resolution = primary.resolution || topResolution;
  }

  model.resolution = raw.resolution || (model.results[0] && model.results[0].resolution) || null;

  // expert review flag from backend
  model.expert_review.candidate_ready = Boolean(raw.needs_expert_review || raw.status === "review_needed" || raw.status === "pending_expert_review");
  if (model.expert_review.candidate_ready) {
    model.expert_review.payload = { root_symptom: model.root_symptom, results: model.results, raw };
  }

  const nq = raw.next_question ?? model.current_question;
  if (typeof nq === "string") {
    const t = nq.trim();
    model.next_question = t ? { question: t } : null;
  } else if (nq && typeof nq === "object") {
    model.next_question = nq;
  } else {
    model.next_question = null;
  }

  return model;
}
