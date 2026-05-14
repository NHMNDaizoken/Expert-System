import { useState } from "react";
import DiagnosisResult from "../components/DiagnosisResult.jsx";
import QuestioningScreen from "../components/QuestioningScreen.jsx";
import SymptomInput from "../components/SymptomInput.jsx";
import { API_ROOT } from "../api/client.js";
import normalizeDiagnosisResult from "../utils/normalizeDiagnosisResult.js";

const DIAGNOSE_URL = `${API_ROOT}/api/diagnose`;
const TOP_K = 5;

export default function DiagnosticChat({ initialState = "input", initialData = null }) {
  const [screenState, setScreenState] = useState(initialState);
  const [sessionId, setSessionId] = useState(initialData?.session_id ?? null);
  const [apiData, setApiData] = useState(() => (initialData ? normalizeDiagnosisResult(initialData) : null));
  const [symptom, setSymptom] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function applyResponse(raw) {
    const data = normalizeDiagnosisResult(raw);
    setApiData(data);
    if (data.session_id) setSessionId(data.session_id);

    const status = raw?.status;
    const isFinal = Boolean(raw?.is_final);
    const hasResults = Array.isArray(data.results) && data.results.length > 0;

    if (
      status === "diagnosed" ||
      status === "inconclusive" ||
      isFinal ||
      data.ui_message ||
      (hasResults && status !== "need_more_info" && status !== "collecting_context")
    ) {
      setScreenState("result");
      return;
    }

    if (
      status === "need_more_info" ||
      status === "collecting_context" ||
      data.next_question ||
      data.current_question ||
      raw?.next_question
    ) {
      setScreenState("questioning");
      return;
    }

    if (data.expert_review?.candidate_ready && !hasResults) {
      setScreenState("review_needed");
      return;
    }

    setScreenState("input");
    setError("Không thể tìm thấy triệu chứng này. Vui lòng thử mô tả khác.");
  }

  async function handleSymptom(event) {
    if (event) event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await fetch(DIAGNOSE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symptom: symptom.trim(), top_k: TOP_K }),
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
    if (!sessionId) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(DIAGNOSE_URL, {
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

  const questioningPayload = apiData?._raw
    ? { ...apiData._raw, ...apiData, next_question: apiData.next_question || apiData._raw.next_question }
    : apiData;

  return (
    <div className="page diagnostic-page">
      <header className="diagnostic-header">
        <h1>Chẩn đoán Lỗi Xe</h1>
        <p>Hệ chuyên gia hỗ trợ tìm ra vấn đề của xe thông qua triệu chứng.</p>
      </header>

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
        <QuestioningScreen data={questioningPayload} onAnswer={handleAnswer} loading={loading} />
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
