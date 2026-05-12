import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { GitBranch, MessageSquareText, ShieldCheck } from "lucide-react";
import DiagnosticChat from "./pages/DiagnosticChat.jsx";
import ExpertReview from "./pages/ExpertReview.jsx";
import GraphViewer from "./pages/GraphViewer.jsx";

const links = [
  { to: "/diagnosis", label: "Chẩn đoán lỗi", icon: MessageSquareText },
  { to: "/graph", label: "Sơ đồ tri thức", icon: GitBranch },
  { to: "/review", label: "Kiểm duyệt luật", icon: ShieldCheck },
];

export default function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">AE</span>
          <div className="brand-text">
            <strong>AutoExpert</strong>
            <small>Hệ chuyên gia chẩn đoán xe</small>
          </div>
        </div>
        <nav>
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to}>
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to="/diagnosis" replace />} />
          <Route path="/diagnosis" element={<DiagnosticChat />} />
          <Route path="/graph" element={<GraphViewer />} />
          <Route path="/review" element={<ExpertReview />} />
        </Routes>
      </main>
    </div>
  );
}
