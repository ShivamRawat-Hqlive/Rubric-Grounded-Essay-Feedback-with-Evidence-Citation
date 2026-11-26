import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { demoApi } from "./api/services";
import type { DemoEvaluation } from "./api/types";

vi.mock("./api/services", () => ({
  appApi: {},
  demoApi: {
    uploadEssay: vi.fn(),
    evaluations: vi.fn(),
    evaluation: vi.fn(),
    review: vi.fn(),
  },
}));

const sourceText = "Evidence supports a claim because it explains the reasoning.";
const demoEvaluation: DemoEvaluation = {
  id: "demo-1",
  filename: "sample.txt",
  created_at: "2026-01-03T00:00:00Z",
  evaluation_mode: "local_demo",
  demo_label: "DEMO-GENERATED — NOT AI",
  status: "needs_review",
  extracted_text: sourceText,
  extractor_name: "UTF-8",
  page_map: [{
    page_number: null,
    extracted_char_start: 0,
    extracted_char_end: sourceText.length,
    extraction_method: "native",
  }],
  total_score: 3.2,
  max_total_score: 5,
  criteria: [{
    name: "Critical thinking",
    description: "Explains reasons and perspectives.",
    weight_percent: 20,
    score: 4,
    max_score: 5,
    weighted_score: 0.8,
    basis: "Demo heuristic: 2 reasoning markers.",
    strengths: ["Reasoning markers appear."],
    areas_to_improve: ["Consider another perspective."],
    suggestions: ["Explain why evidence matters."],
    evidence_quotes: [{
      quoted_text: sourceText,
      extracted_char_start: 0,
      extracted_char_end: sourceText.length,
      page_number: null,
      existence_verified: true,
    }],
  }],
  faculty_note: null,
};

function renderApp(path = "/") {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <App />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(demoApi.evaluations).mockResolvedValue([]);
  vi.mocked(demoApi.evaluation).mockResolvedValue(demoEvaluation);
});

test("home explains and links to both local demonstration modes", () => {
  renderApp("/");
  expect(screen.getByRole("heading", { name: /Evidence-grounded essay feedback/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Start student demo" })).toHaveAttribute("href", "/student");
  expect(screen.getByRole("link", { name: "Open faculty review" })).toHaveAttribute("href", "/faculty");
});

test("student route presents PDF and TXT submission without login", () => {
  renderApp("/student");
  expect(screen.getByRole("heading", { name: "Submit an essay" })).toBeInTheDocument();
  expect(screen.getByLabelText("Essay file")).toHaveAttribute(
    "accept",
    ".pdf,application/pdf,.txt,text/plain",
  );
});

test("faculty can approve a demo result from the review queue", async () => {
  vi.mocked(demoApi.evaluations).mockResolvedValue([demoEvaluation]);
  vi.mocked(demoApi.review).mockResolvedValue({
    ...demoEvaluation,
    status: "approved",
  });
  renderApp("/faculty");

  fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
  await waitFor(() => expect(demoApi.review).toHaveBeenCalledWith(
    "demo-1",
    "approved",
  ));
  expect(await screen.findByText("Review status: approved")).toBeInTheDocument();
});

test("student results reveal criteria only after faculty approval", async () => {
  renderApp("/student/essays/demo-1");

  expect(await screen.findByText(/Faculty review is pending/i)).toBeInTheDocument();
  expect(screen.queryByText("Critical thinking")).not.toBeInTheDocument();
});

test("approved student results show criterion feedback and verified evidence", async () => {
  vi.mocked(demoApi.evaluation).mockResolvedValue({
    ...demoEvaluation,
    status: "approved",
  });
  renderApp("/student/essays/demo-1");

  expect(await screen.findByRole("heading", { name: "Critical thinking" })).toBeInTheDocument();
  expect(screen.getByText(sourceText)).toBeInTheDocument();
  expect(screen.getByText(/Characters 0–/)).toBeInTheDocument();
});
