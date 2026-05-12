import { useState } from "react";
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
    if (data.status === "diagnosed" || data.status === "llm_fallback") {
      <div className="result-card warning">
        <h2>Chưa có luật phù hợp trong cơ sở tri thức</h2>
        <p>
          Triệu chứng này đã được đưa vào hàng chờ kiểm duyệt.
          Quản trị viên cần duyệt trước khi thêm vào luật chẩn đoán.
        </p>
      </div>
    } else if (data.status === "need_more_info") {
      setScreenState("questioning");
    } else {
      setScreenState("input");
      setError("Không thể tìm thấy triệu chứng này. Vui lòng thử mô tả khác.");
    }
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
      const sid = await ensureSession();
      const response = await fetch(`${API_ROOT}/diagnose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sid, symptom }),
      });
      applyResponse(await response.json());
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
      const response = await fetch(`${API_ROOT}/diagnose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, step_answer: answer }),
      });
      applyResponse(await response.json());
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

      {screenState === "result" && (
        <DiagnosisResult data={apiData} onRestart={handleRestart} />
      )}
    </div>
  );
}
