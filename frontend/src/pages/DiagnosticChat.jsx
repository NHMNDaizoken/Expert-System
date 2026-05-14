import { useState } from "react";
import { Check, HelpCircle, Send, X } from "lucide-react";
import DiagnosisResult from "../components/DiagnosisResult.jsx";
import QuestioningScreen from "../components/QuestioningScreen.jsx";
import SymptomInput from "../components/SymptomInput.jsx";
import { API_ROOT } from "../api/client.js";

export default function DiagnosticChat({ initialState = "input", initialData = null }) {
  const [screenState, setScreenState] = useState(initialState);
  const [sessionId, setSessionId] = useState(initialData?.session_id ?? null);
  const [apiData, setApiData] = useState(initialData);
  const [symptom, setSymptom] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function applyResponse(data) {
    setApiData(data);
    if (data.session_id) {
      setSessionId(data.session_id);
    }

    const decisionTree = data?.decision_tree || data?.llm_patch_suggestion;
    if (
      data?.type === "diagnostic_decision_tree" ||
      data?.type === "question" ||
      decisionTree?.type === "diagnostic_decision_tree"
    ) {
      setScreenState("decision_tree");
      return;
    }

    if (data?.type === "result" && data?.result_node) {
      setScreenState("tree_result");
      return;
    }

    // Restore the expert-system loop: if the backend provides a next question,
    // we keep asking instead of jumping to a result screen.
    if (data?.next_question || data?.status === "need_more_info" || data?.status === "collecting_context") {
      setScreenState("questioning");
      return;
    }

    if (data?.status === "diagnosed") {
      setScreenState("result");
      return;
    }

    if (data?.status === "llm_fallback" || data?.status === "review_needed") {
      setScreenState("review_needed");
      return;
    }

    setScreenState("input");
    setError("Không thể tìm thấy triệu chứng này. Vui lòng thử mô tả khác.");
  }

  async function ensureSession() {
    if (sessionId) {
      return sessionId;
    }
    const response = await fetch(`${API_ROOT}/session/new`, { method: "POST" });
    const data = await response.json();
    setSessionId(data.session_id);
    return data.session_id;
  }

  async function handleSymptom(event) {
    if (event) event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_ROOT}/api/diagnosis/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: symptom }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || "Không gọi được API chẩn đoán.");
      }
      applyResponse(data);
    } catch (err) {
      setError(err.message);
      setScreenState("input");
    } finally {
      setLoading(false);
    }
  }

  async function handleAnswer(answer) {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_ROOT}/api/diagnosis/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, step_answer: answer }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || "Không gửi được câu trả lời.");
      }
      applyResponse(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleTreeAnswer(answer) {
    const nodeId = apiData?.current_node?.node_id;
    if (!sessionId || !nodeId) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_ROOT}/api/diagnosis/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, node_id: nodeId, answer }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || "Không gửi được câu trả lời.");
      }
      applyResponse(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function deleteSession(sid) {
    if (!sid) {
      return;
    }
    try {
      await fetch(`${API_ROOT}/session/${encodeURIComponent(sid)}`, {
        method: "DELETE",
      });
    } catch {
      // Reset UI even if the old server-side session was already gone.
    }
  }

  function handleUnlock() {
    const sid = sessionId;
    setScreenState("input");
    setSessionId(null);
    setApiData(null);
    setError("");
    void deleteSession(sid);
  }

  function handleRestart() {
    setScreenState("input");
    setSessionId(null);
    setApiData(null);
    setSymptom("");
    setError("");
  }

  return (
    <div className="page diagnostic-page">
      <header className="diagnostic-header">
        <h1>Chẩn đoán Lỗi Xe</h1>
        <p>Hệ chuyên gia hỗ trợ tìm ra vấn đề của xe thông qua triệu chứng.</p>
      </header>

      {/* Stacked Layout: Input is always rendered, but its appearance changes based on screenState */}
      <SymptomInput
        value={symptom}
        onChange={setSymptom}
        onSubmit={handleSymptom}
        loading={loading && screenState === "input"}
        error={error}
        isLocked={screenState !== "input"}
        onUnlock={handleUnlock}
      />

      {screenState === "questioning" && (
        <QuestioningScreen data={apiData} onAnswer={handleAnswer} loading={loading} />
      )}

      {screenState === "decision_tree" && (
        <DecisionTreeQuestion data={apiData} onAnswer={handleTreeAnswer} loading={loading} error={error} />
      )}

      {screenState === "tree_result" && (
        <DecisionTreeResult data={apiData} onRestart={handleRestart} />
      )}

      {screenState === "result" && (
        <DiagnosisResult data={apiData} onRestart={handleRestart} />
      )}

      {screenState === "review_needed" && (
        <DiagnosisResult data={apiData} onRestart={handleRestart} />
      )}
    </div>
  );
}

function DecisionTreeQuestion({ data, onAnswer, loading, error }) {
  const rootSymptom = data?.root_symptom;
  const currentNode = data?.current_node || {};
  const answers = data?.answers || [];
  const progress = data?.progress || {};
  return (
    <section className="question-card decision-tree-card">
      <div className="question-header">
        <div>
          <span className="eyebrow">Cây chẩn đoán LLM</span>
          <h2>{rootSymptom?.label_vi || "Triệu chứng ban đầu"}</h2>
          <p className="muted">Bước {progress.current_depth || 1}/{progress.estimated_max_depth || "?"}</p>
        </div>
      </div>
      <div className="question-box">
        <h3>{currentNode.question}</h3>
        {currentNode.purpose && <p className="muted">{currentNode.purpose}</p>}
      </div>
      <div className="answer-actions">
        <button type="button" onClick={() => onAnswer("yes")} disabled={loading}>
          <Check size={18} />
          Có
        </button>
        <button type="button" className="secondary-btn" onClick={() => onAnswer("no")} disabled={loading}>
          <X size={18} />
          Không
        </button>
        <button type="button" className="secondary-btn" onClick={() => onAnswer("unknown")} disabled={loading}>
          <HelpCircle size={18} />
          Không rõ
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <AnswerPath answers={answers} />
    </section>
  );
}

function DecisionTreeResult({ data, onRestart }) {
  const result = data?.result_node || {};
  const fault = result.fault || {};
  return (
    <section className="result-card decision-tree-result">
      <div className="result-header">
        <div>
          <span className="eyebrow">Kết quả từ cây chẩn đoán</span>
          <h2>{fault.fault_name || "Kết quả chẩn đoán"}</h2>
          <p className="muted">Độ tin cậy {Math.round(Number(fault.confidence || 0) * 100)}%</p>
        </div>
      </div>
      <AnswerPath answers={data?.selected_path || []} />
      <InfoList title="Bộ phận ảnh hưởng" items={(result.components || []).map((item) => item.name_vi || item.component_id)} />
      <InfoList title="Nguyên nhân có thể" items={result.causes} />
      <InfoList title="Cách kiểm tra" items={result.diagnostic_steps} />
      <InfoList title="Cách sửa" items={result.repair_steps} />
      <InfoList title="Lưu ý an toàn" items={result.safety_notes} />
      <div className="answer-actions">
        <button type="button" disabled title="Cây đã được gửi vào hàng chờ khi tạo">
          <Send size={18} />
          Gửi chuyên gia duyệt
        </button>
        <button type="button" className="secondary-btn" onClick={onRestart}>
          Chẩn đoán triệu chứng khác
        </button>
      </div>
    </section>
  );
}

function AnswerPath({ answers }) {
  if (!answers?.length) return null;
  const labels = { yes: "Có", no: "Không", unknown: "Không rõ" };
  return (
    <div className="selected-path">
      <h3>Đường trả lời đã chọn</h3>
      {answers.map((item, index) => (
        <div className="path-row" key={`${item.node_id}-${index}`}>
          <span>{index + 1}</span>
          <p>{item.question}</p>
          <strong>{labels[item.answer] || item.answer}</strong>
        </div>
      ))}
    </div>
  );
}

function InfoList({ title, items }) {
  const values = (items || []).filter(Boolean);
  if (!values.length) return null;
  return (
    <section className="result-section">
      <h3>{title}</h3>
      <ul>
        {values.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
