import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import DiagnosticChat from "../pages/DiagnosticChat.jsx";

const mockFetch = vi.fn();
global.fetch = mockFetch;

const needMoreInfoResponse = {
  session_id: "s1",
  status: "need_more_info",
  next_question: { question: "Do you hear a rapid clicking sound when turning the key?" },
  step_progress: "1/3",
  step_context: "Starting system",
  fault_preview: { fault_id: "battery_weak", fault_name: "Weak Battery", score: 0.64 },
  mode: "procedure_tree",
};

const diagnosedResponse = {
  session_id: "s1",
  status: "diagnosed",
  results: [
    { fault_id: "battery_weak", fault_name: "Weak / Dead Battery", score: 0.87 },
    { fault_id: "cable_corroded", fault_name: "Corroded Battery Cables", score: 0.1 },
  ],
  resolution: {
    parts: ["12V Battery", "Battery Clamp"],
    procedure: "Measure battery voltage. Replace if under 12.4V.",
    difficulty: "easy",
    labor_hours: 1,
  },
};

describe("DiagnosticChat state machine", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  test("starts at input screen", () => {
    render(<DiagnosticChat />);
    expect(screen.getByLabelText(/describe what is happening with your car/i)).toBeInTheDocument();
    expect(screen.getByText(/xe khó nổ/i)).toBeInTheDocument();
  });

  test("switches to questioning screen when API returns need_more_info", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ session_id: "s1" }) });
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => needMoreInfoResponse });
    render(<DiagnosticChat />);
    fireEvent.change(screen.getByLabelText(/describe what is happening with your car/i), { target: { value: "hard to start" } });
    fireEvent.click(screen.getByText(/bắt đầu chẩn đoán/i));
    await waitFor(() => expect(screen.getByText(/rapid clicking/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /^có$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^không$/i })).toBeInTheDocument();
  });

  test("does not display fault preview while asking follow-up questions", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ session_id: "s1" }) });
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => needMoreInfoResponse });
    render(<DiagnosticChat />);
    fireEvent.change(screen.getByLabelText(/describe what is happening with your car/i), { target: { value: "hard to start" } });
    fireEvent.click(screen.getByText(/bắt đầu chẩn đoán/i));
    await waitFor(() => expect(screen.getByText(/rapid clicking/i)).toBeInTheDocument());
    expect(screen.queryByText(/weak battery/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/64%/)).not.toBeInTheDocument();
  });

  test("progress bar correctly shows step_progress", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ session_id: "s1" }) });
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => needMoreInfoResponse });
    render(<DiagnosticChat />);
    fireEvent.change(screen.getByLabelText(/describe what is happening with your car/i), { target: { value: "hard to start" } });
    fireEvent.click(screen.getByText(/bắt đầu chẩn đoán/i));
    await waitFor(() => expect(screen.getByText(/bước 1 \/ 3/i)).toBeInTheDocument());
  });

  test("switches to result screen when API returns diagnosed", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ session_id: "s1" }) });
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => needMoreInfoResponse });
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => diagnosedResponse });
    render(<DiagnosticChat />);
    fireEvent.change(screen.getByLabelText(/describe what is happening with your car/i), { target: { value: "hard to start" } });
    fireEvent.click(screen.getByText(/bắt đầu chẩn đoán/i));
    await waitFor(() => screen.getByRole("button", { name: /^có$/i }));
    fireEvent.click(screen.getByRole("button", { name: /^có$/i }));
    await waitFor(() => expect(screen.getByText(/12V Battery/i)).toBeInTheDocument());
    expect(screen.getByText(/87%/)).toBeInTheDocument();
  });

  test("resolution displays parts and procedure", () => {
    render(<DiagnosticChat initialState="result" initialData={diagnosedResponse} />);
    expect(screen.getByText(/12V Battery/i)).toBeInTheDocument();
    expect(screen.getByText(/Battery Clamp/i)).toBeInTheDocument();
    expect(screen.getByText(/Measure battery voltage/i)).toBeInTheDocument();
  });

  test("restart button returns to input screen", () => {
    render(<DiagnosticChat initialState="result" initialData={diagnosedResponse} />);
    fireEvent.click(screen.getByText(/chẩn đoán lỗi khác/i));
    expect(screen.getByLabelText(/describe what is happening with your car/i)).toBeInTheDocument();
  });
});
