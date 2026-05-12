import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import DiagnosticChat from "../pages/DiagnosticChat.jsx";

const mockFetch = vi.fn();
global.fetch = mockFetch;

const needMoreInfoResponse = {
  session_id: "s1",
  status: "need_more_info",
  next_question: { question: "Bạn có nghe tiếng tạch tạch nhanh khi vặn chìa khóa không?" },
  step_progress: "1",
  step_context: "Hệ thống khởi động",
  fault_preview: { fault_id: "battery_weak", fault_name: "Ắc quy yếu", score: 0.64 },
  mode: "procedure_tree",
};

const diagnosedResponse = {
  session_id: "s1",
  status: "diagnosed",
  results: [
    { fault_id: "battery_weak", fault_name: "Ắc quy yếu/hỏng", score: 0.87 },
    { fault_id: "cable_corroded", fault_name: "Cọc cáp ắc quy bị oxy hóa", score: 0.1 },
  ],
  resolution: {
    parts: ["Ắc quy 12V", "Kẹp cọc ắc quy"],
    procedure: "Đo điện áp ắc quy. Thay nếu dưới 12.4V.",
    difficulty: "easy",
    labor_hours: 1,
  },
};

describe("Luồng DiagnosticChat", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  test("hiển thị màn nhập triệu chứng ban đầu", () => {
    render(<DiagnosticChat />);
    expect(
      screen.getByLabelText(/mô tả hiện tượng đang xảy ra với xe/i)
    ).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/xe khó nổ/i)).toBeInTheDocument();
  });

  test("chuyển sang màn hỏi thêm khi API trả need_more_info", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ session_id: "s1" }) });
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => needMoreInfoResponse });
    render(<DiagnosticChat />);
    fireEvent.change(screen.getByLabelText(/mô tả hiện tượng đang xảy ra với xe/i), {
      target: { value: "xe khó nổ" },
    });
    fireEvent.click(screen.getByText(/bắt đầu chẩn đoán/i));
    await waitFor(() => expect(screen.getByText(/tạch tạch nhanh/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /^có$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^không$/i })).toBeInTheDocument();
  });

  test("không hiển thị lỗi xem trước khi đang hỏi thêm", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ session_id: "s1" }) });
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => needMoreInfoResponse });
    render(<DiagnosticChat />);
    fireEvent.change(screen.getByLabelText(/mô tả hiện tượng đang xảy ra với xe/i), {
      target: { value: "xe khó nổ" },
    });
    fireEvent.click(screen.getByText(/bắt đầu chẩn đoán/i));
    await waitFor(() => expect(screen.getByText(/tạch tạch nhanh/i)).toBeInTheDocument());
    expect(screen.queryByText(/ắc quy yếu/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/64%/)).not.toBeInTheDocument();
  });

  test("thanh tiến trình hiển thị số bước hiện tại", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ session_id: "s1" }) });
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => needMoreInfoResponse });
    render(<DiagnosticChat />);
    fireEvent.change(screen.getByLabelText(/mô tả hiện tượng đang xảy ra với xe/i), {
      target: { value: "xe khó nổ" },
    });
    fireEvent.click(screen.getByText(/bắt đầu chẩn đoán/i));
    await waitFor(() => expect(screen.getByText(/^bước 1$/i)).toBeInTheDocument());
  });

  test("chuyển sang màn kết quả khi API trả diagnosed", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ session_id: "s1" }) });
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => needMoreInfoResponse });
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => diagnosedResponse });
    render(<DiagnosticChat />);
    fireEvent.change(screen.getByLabelText(/mô tả hiện tượng đang xảy ra với xe/i), {
      target: { value: "xe khó nổ" },
    });
    fireEvent.click(screen.getByText(/bắt đầu chẩn đoán/i));
    await waitFor(() => screen.getByRole("button", { name: /^có$/i }));
    fireEvent.click(screen.getByRole("button", { name: /^có$/i }));
    await waitFor(() => expect(screen.getByText(/Ắc quy 12V/i)).toBeInTheDocument());
    expect(screen.getByText(/87%/)).toBeInTheDocument();
  });

  test("hiển thị linh kiện và quy trình sửa chữa", () => {
    render(<DiagnosticChat initialState="result" initialData={diagnosedResponse} />);
    expect(screen.getByText(/Ắc quy 12V/i)).toBeInTheDocument();
    expect(screen.getByText(/Kẹp cọc ắc quy/i)).toBeInTheDocument();
    expect(screen.getByText(/Đo điện áp ắc quy/i)).toBeInTheDocument();
  });

  test("nút chẩn đoán lại quay về màn nhập", () => {
    render(<DiagnosticChat initialState="result" initialData={diagnosedResponse} />);
    fireEvent.click(screen.getByText(/chẩn đoán lỗi khác/i));
    expect(
      screen.getByLabelText(/mô tả hiện tượng đang xảy ra với xe/i)
    ).toBeInTheDocument();
  });

  test("nút sửa mô tả reset kết quả hiện tại và xóa session", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ deleted: true }) });
    render(<DiagnosticChat initialState="result" initialData={diagnosedResponse} />);
    expect(screen.getByText(/87%/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/sửa mô tả/i));
    await waitFor(() => expect(screen.queryByText(/87%/)).not.toBeInTheDocument());
    expect(
      screen.getByLabelText(/mô tả hiện tượng đang xảy ra với xe/i)
    ).toBeInTheDocument();
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining("/session/s1"), {
      method: "DELETE",
    });
  });
});
