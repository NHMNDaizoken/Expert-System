import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Battery,
  Check,
  Disc,
  Droplet,
  Settings,
  Thermometer,
} from "lucide-react";
import { getGraph } from "../api/client.js";

const QUICK_CHIPS = [
  "Mùi nhiên liệu từ xe",
  "Động cơ hụt hơi ở tốc độ cao",
  "Gầm xe kêu hoặc rung không đều",
  "Phanh bị lệch",
  "Mất công suất",
  "Có tiếng kêu lạ",
  "Xe hao xăng",
  "Điều hòa không lạnh",
];

const CATEGORY_DEF = [
  { id: "engine", name: "Engine", label: "Động cơ", icon: Activity, keywords: ["engine", "idle", "acceleration", "power", "stall", "misfire", "động cơ", "máy"] },
  { id: "fuel", name: "Fuel", label: "Nhiên liệu", icon: Droplet, keywords: ["fuel", "xăng", "nhiên liệu", "hao xăng", "mùi xăng"] },
  { id: "electrical", name: "Electrical", label: "Điện", icon: Battery, keywords: ["light", "battery", "voltage", "door lock", "headlight", "glow plug", "đèn", "ắc quy", "điện"] },
  { id: "cooling", name: "Cooling", label: "Làm mát", icon: Thermometer, keywords: ["coolant", "overheat", "nóng máy", "quá nhiệt", "két nước"] },
  { id: "brake", name: "Brake", label: "Phanh", icon: Disc, keywords: ["brake", "abs", "phanh", "thắng"] },
  { id: "other", name: "Other", label: "Hệ thống khác", icon: Settings, keywords: [] },
];

function humanizeId(id = "") {
  return id
    .replace(/^SYM_/i, "")
    .replace(/_/g, " ")
    .toLowerCase();
}

function displayLabel(id, item = {}) {
  return item.label_vi || item.display_name || item.name || humanizeId(id);
}

function categorize(aliases) {
  const allSymptoms = Object.entries(aliases).map(([id, item]) => ({
    id,
    label: displayLabel(id, item),
    relatedFaults: item.relatedFaults || 0,
  }));

  const result = CATEGORY_DEF.map((cat) => ({ ...cat, symptoms: [] }));
  const otherCat = result.find((cat) => cat.id === "other");

  allSymptoms.forEach((sym) => {
    const lowerName = `${sym.id} ${sym.label}`.toLowerCase();
    let matched = false;
    for (const cat of result) {
      if (cat.id !== "other" && cat.keywords.some((kw) => lowerName.includes(kw))) {
        cat.symptoms.push(sym);
        matched = true;
        break;
      }
    }
    if (!matched) otherCat.symptoms.push(sym);
  });

  return result.filter((cat) => cat.symptoms.length > 0);
}

function symptomsFromGraph(data) {
  const symptomsObj = {};
  const relatedFaults = {};
  (data.edges || [])
    .filter((edge) => edge.type === "HAS_SYMPTOM")
    .forEach((edge) => {
      relatedFaults[edge.target] = (relatedFaults[edge.target] || 0) + 1;
      relatedFaults[edge.source] = (relatedFaults[edge.source] || 0) + 1;
    });

  (data.nodes || [])
    .filter((node) => node.type === "Symptom")
    .forEach((node) => {
      symptomsObj[node.id] = {
        name: node.id,
        display_name: node.label || humanizeId(node.id),
        label_vi: node.metadata?.label_vi,
        relatedFaults: relatedFaults[node.id] || 0,
      };
    });
  return symptomsObj;
}

function appendPhrase(currentValue, phrase) {
  const text = currentValue.trim();
  if (!text) return phrase;
  if (text.toLowerCase().includes(phrase.toLowerCase())) return currentValue;
  return `${text}, ${phrase}`;
}

export default function SymptomInput({ value, onChange, onSubmit, loading, error, isLocked, onUnlock }) {
  const [searchQuery, setSearchQuery] = useState("");
  const [categories, setCategories] = useState([]);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  useEffect(() => {
    if (!advancedOpen || categories.length > 0) return;
    getGraph()
      .then((data) => setCategories(categorize(symptomsFromGraph(data))))
      .catch(() => setCategories([]));
  }, [advancedOpen, categories.length]);

  const selectedList = useMemo(() => {
    return value
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
  }, [value]);

  function addQuickChip(label) {
    if (isLocked) return;
    onChange(appendPhrase(value, label));
  }

  function toggleSymptom(label) {
    if (isLocked) return;
    const current = [...selectedList];
    if (current.includes(label)) {
      onChange(current.filter((item) => item !== label).join(", "));
    } else {
      onChange([...current, label].join(", "));
    }
  }

  if (isLocked) {
    return (
      <section className="interview-summary glass-panel">
        <div>
          <span className="eyebrow">Mô tả ban đầu</span>
          <p>{value || "Chưa có mô tả"}</p>
        </div>
        <button className="secondary-btn" onClick={onUnlock}>
          <Settings size={16} /> Sửa mô tả
        </button>
      </section>
    );
  }

  return (
    <section className="diagnostic-input">
      <form className="interview-input-card glass-panel" onSubmit={onSubmit}>
        <label htmlFor="symptom-description">Mô tả hiện tượng đang xảy ra với xe</label>
        <textarea
          id="symptom-description"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Ví dụ: Xe khó nổ vào buổi sáng, có tiếng tạch tạch khi vặn chìa khóa..."
        />

        <div className="quick-chip-group" aria-label="Gợi ý nhanh">
          {QUICK_CHIPS.map((chip) => (
            <button
              type="button"
              key={chip}
              className="quick-chip"
              onClick={() => addQuickChip(chip)}
            >
              {chip}
            </button>
          ))}
        </div>

        {error && <div className="error">{error}</div>}

        <div className="interview-actions">
          <button
            type="button"
            className="secondary-btn"
            onClick={() => setAdvancedOpen((open) => !open)}
            aria-expanded={advancedOpen}
          >
            <Settings size={16} />
            {advancedOpen ? "Ẩn chế độ thợ máy" : "Chế độ thợ máy"}
          </button>
          <button className="primary-btn" type="submit" disabled={loading || !value.trim()}>
            {loading ? "Đang phân tích..." : "Bắt đầu chẩn đoán"}
          </button>
        </div>
      </form>

      {advancedOpen && (
        <div className="advanced-symptom-panel glass-panel">
          <div className="advanced-panel-header">
            <div>
              <h2>Chế độ thợ máy</h2>
              <p>Chọn nhanh triệu chứng kỹ thuật nếu bạn đã biết rõ biểu hiện.</p>
            </div>
          </div>

          <input
            type="text"
            placeholder="Tìm triệu chứng kỹ thuật..."
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
          />

          <div className="symptom-categories">
            {categories.map((cat) => {
              const filtered = cat.symptoms.filter((sym) =>
                sym.label.toLowerCase().includes(searchQuery.toLowerCase())
              );
              if (filtered.length === 0) return null;

              const Icon = cat.icon;
              return (
                <div key={cat.id} className="category-card">
                  <div className="category-header">
                    <Icon size={18} />
                    <span>{cat.label}</span>
                  </div>
                  <div className="symptom-toggle-list">
                    {filtered.map((sym) => {
                      const isSelected = selectedList.includes(sym.label);
                      return (
                        <button
                          type="button"
                          key={sym.id}
                          className={`symptom-toggle symptom-row ${isSelected ? "selected" : ""}`}
                          onClick={() => toggleSymptom(sym.label)}
                        >
                          <span className="checkbox-mark" aria-hidden="true">
                            {isSelected && <Check size={12} color="white" strokeWidth={3} />}
                          </span>
                          <span className="symptom-row-text">
                            <span className="symptom-row-title" title={sym.label}>
                              {sym.label}
                            </span>
                            <span className="symptom-row-meta">
                              {cat.label} · {sym.relatedFaults} lỗi liên quan trong KG
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
