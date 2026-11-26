import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { appApi } from "../api/services";
import type {
  Course,
  CriterionScore,
  Essay,
  EssayText,
  Evaluation,
  ReviewEvent,
  Rubric,
  RubricVersion,
} from "../api/types";
import { EvaluationResults } from "../components/evaluations/EvaluationResults";
import { FacultyReviewPage } from "./faculty/FacultyReviewPage";
import { StudentDashboard } from "./student/StudentDashboard";
import { EssayDetailPage } from "./student/EssayDetailPage";

vi.mock("../api/services", () => ({
  appApi: {
    courses: vi.fn(),
    availableCourses: vi.fn(),
    enrollInCourse: vi.fn(),
    essays: vi.fn(),
    essay: vi.fn(),
    essayText: vi.fn(),
    uploadEssay: vi.fn(),
    rubrics: vi.fn(),
    rubricVersions: vi.fn(),
    rubricVersion: vi.fn(),
    evaluations: vi.fn(),
    evaluation: vi.fn(),
    startEvaluation: vi.fn(),
    reviewQueue: vi.fn(),
    updateCriterion: vi.fn(),
    addReviewNote: vi.fn(),
    reviewEvaluation: vi.fn(),
  },
}));

const course: Course = {
  id: "course-1",
  name: "Writing Studies",
  code: "WRT101",
  created_by_id: "faculty-1",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const essay: Essay = {
  id: "essay-1",
  student_id: "student-1",
  course_id: course.id,
  original_filename: "argument.txt",
  content_type: "text/plain",
  size_bytes: 256,
  parse_status: "parsed",
  normalizer_version: "1",
  page_map: [],
  extractor_name: "plain_text",
  extractor_version: "1",
  sha256: "synthetic-hash",
  created_at: "2026-01-02T00:00:00Z",
};

const sourceText = "A strong thesis uses evidence. The essay develops its claim.";
const quotedText = "A strong thesis uses evidence.";
const quoteStart = sourceText.indexOf(quotedText);

const essayText: EssayText = {
  extracted_text: sourceText,
  normalized_text: sourceText,
  normalizer_version: "1",
  offset_alignment: [],
  page_map: [],
};

const criterion = {
  id: "criterion-1",
  rubric_version_id: "version-1",
  name: "Argument",
  description: "Develop a clear, evidence-supported argument.",
  levels: [{ score: "2", description: "Developing" }],
  min_score: "0",
  max_score: "4",
  weight: "1",
  sort_order: 0,
};

const rubric: Rubric = {
  id: "rubric-1",
  course_id: course.id,
  created_by_id: "faculty-1",
  title: "Argument rubric",
  description: null,
  status: "published",
  created_at: "2026-01-01T00:00:00Z",
};

const rubricVersion: RubricVersion = {
  id: "version-1",
  rubric_id: rubric.id,
  version_number: 1,
  is_published: true,
  published_at: "2026-01-01T00:00:00Z",
  snapshot: null,
  criteria: [criterion],
};

const citation = {
  source_chunk_id: "chunk-1",
  quoted_text: quotedText,
  model_relevance_rationale: "It states the central claim.",
  existence_status: "verified" as const,
  relevance_status: "unverified" as const,
  extracted_char_start: quoteStart,
  extracted_char_end: quoteStart + quotedText.length,
  normalized_char_start: quoteStart,
  normalized_char_end: quoteStart + quotedText.length,
  paragraph_start: 1,
  paragraph_end: 1,
  page_start: null,
  page_end: null,
};

const criterionScore: CriterionScore = {
  id: "score-1",
  criterion_id: criterion.id,
  ai_score: "2.0000",
  ai_rationale: "The argument is present but needs more development.",
  strengths: ["A clear central claim."],
  weaknesses: ["Counterarguments need attention."],
  suggestions: ["Address an opposing view."],
  claims: [
    {
      text: "The essay states a thesis.",
      evidence_quotes: [citation],
    },
  ],
  faculty_score: null,
  faculty_rationale: null,
  faculty_strengths: null,
  faculty_weaknesses: null,
  faculty_suggestions: null,
};

const baseEvaluation: Evaluation = {
  id: "evaluation-1",
  essay_id: essay.id,
  rubric_version_id: rubricVersion.id,
  requested_by_id: essay.student_id,
  evaluation_mode: "openai",
  status: "needs_review",
  ai_total_score: "2.0000",
  faculty_total_score: null,
  has_unsupported_flags: false,
  error_code: null,
  started_at: "2026-01-03T00:00:00Z",
  completed_at: "2026-01-03T00:01:00Z",
  criterion_scores: [criterionScore],
  review_history: [],
};

function renderStudentDashboard() {
  return render(
    <MemoryRouter
      initialEntries={["/student"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/student" element={<StudentDashboard />} />
        <Route path="/student/essays/:essayId" element={<p>Essay detail route opened</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderEssayDetail() {
  return render(
    <MemoryRouter
      initialEntries={["/student/essays/essay-1"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/student/essays/:essayId" element={<EssayDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderFacultyReview() {
  return render(
    <MemoryRouter
      initialEntries={["/faculty/reviews/evaluation-1"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route
          path="/faculty/reviews/:evaluationId"
          element={<FacultyReviewPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(appApi.courses).mockResolvedValue([course]);
  vi.mocked(appApi.availableCourses).mockResolvedValue([]);
  vi.mocked(appApi.essays).mockResolvedValue([essay]);
  vi.mocked(appApi.essay).mockResolvedValue(essay);
  vi.mocked(appApi.essayText).mockResolvedValue(essayText);
  vi.mocked(appApi.uploadEssay).mockResolvedValue(essay);
  vi.mocked(appApi.enrollInCourse).mockResolvedValue({
    id: "enrollment-1",
    course_id: course.id,
    user_id: "student-1",
    role: "student",
    created_at: "2026-01-02T00:00:00Z",
  });
  vi.mocked(appApi.rubrics).mockResolvedValue([rubric]);
  vi.mocked(appApi.rubricVersions).mockResolvedValue([rubricVersion]);
  vi.mocked(appApi.rubricVersion).mockResolvedValue(rubricVersion);
  vi.mocked(appApi.evaluations).mockResolvedValue([]);
  vi.mocked(appApi.evaluation).mockResolvedValue(baseEvaluation);
  vi.mocked(appApi.startEvaluation).mockResolvedValue(baseEvaluation);
  vi.mocked(appApi.reviewQueue).mockResolvedValue([]);
});

test("uploads an essay to an enrolled course", async () => {
  renderStudentDashboard();

  const file = new File(["A short essay"], "argument.txt", {
    type: "text/plain",
  });
  fireEvent.change(await screen.findByLabelText("Enrolled course"), {
    target: { value: course.id },
  });
  const fileInput = screen.getByLabelText("Essay file") as HTMLInputElement;
  Object.defineProperty(fileInput, "files", {
    configurable: true,
    value: [file],
  });
  fireEvent.change(fileInput);
  fireEvent.submit(fileInput.closest("form")!);

  await waitFor(() =>
    expect(appApi.uploadEssay).toHaveBeenCalledWith(file, course.id),
  );
  expect(await screen.findByText("Essay detail route opened")).toBeInTheDocument();
});

test("enrolls in an available course and refreshes the upload course list", async () => {
  vi.mocked(appApi.courses)
    .mockResolvedValueOnce([])
    .mockResolvedValue([course]);
  vi.mocked(appApi.availableCourses)
    .mockResolvedValueOnce([{ ...course, faculty_name: "Professor" }])
    .mockResolvedValue([]);
  renderStudentDashboard();

  expect(await screen.findByText("Available Courses")).toBeInTheDocument();
  expect(await screen.findByText("Faculty: Professor")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Enroll" }));

  expect(await screen.findByRole("status")).toHaveTextContent(
    "You are now enrolled in Writing Studies.",
  );
  await waitFor(() =>
    expect(appApi.enrollInCourse).toHaveBeenCalledWith(course.id),
  );
  expect(screen.getByLabelText("Enrolled course")).toHaveValue(course.id);
  expect(screen.getByRole("button", { name: "Upload essay" })).toBeEnabled();
  expect(screen.getByText("Writing Studies")).toBeInTheDocument();
  expect(screen.getByText("Courses").parentElement).toHaveTextContent("1");
});

test("shows an enrollment error from the API", async () => {
  vi.mocked(appApi.courses).mockResolvedValue([]);
  vi.mocked(appApi.availableCourses).mockResolvedValue([course]);
  vi.mocked(appApi.enrollInCourse).mockRejectedValue(
    new Error("Course is no longer available."),
  );
  renderStudentDashboard();

  fireEvent.click(await screen.findByRole("button", { name: "Enroll" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Unable to enroll in this course.",
  );
});

test("starts an evaluation with a selected published rubric and labels mock mode", async () => {
  const mockEvaluation = {
    ...baseEvaluation,
    evaluation_mode: "mock" as const,
  };
  vi.mocked(appApi.startEvaluation).mockResolvedValue(mockEvaluation);
  vi.mocked(appApi.evaluations)
    .mockResolvedValueOnce([])
    .mockResolvedValue([mockEvaluation]);
  renderEssayDetail();

  fireEvent.click(
    await screen.findByRole("button", { name: "Start evaluation" }),
  );

  await waitFor(() =>
    expect(appApi.startEvaluation).toHaveBeenCalledWith(essay.id, rubricVersion.id),
  );
  expect(
    await screen.findByText("MOCK — NOT AI-GENERATED"),
  ).toBeInTheDocument();
});

test("shows approved criterion results and highlights only an exact evidence offset", () => {
  const approvedEvaluation: Evaluation = {
    ...baseEvaluation,
    status: "approved",
    criterion_scores: [
      {
        ...criterionScore,
        faculty_score: "3.5000",
      },
    ],
    faculty_total_score: "3.5000",
  };
  const { container } = render(
    <EvaluationResults
      evaluation={approvedEvaluation}
      criteria={[criterion]}
      sourceText={sourceText}
      audience="student"
    />,
  );

  expect(screen.getByText("Weighted total: 3.5000")).toBeInTheDocument();
  expect(screen.getByText("Approved score")).toBeInTheDocument();
  expect(screen.getByText("Original AI score: 2.0000")).toBeInTheDocument();
  expect(screen.getByText("Relevance unverified")).toBeInTheDocument();
  expect(container.querySelector("mark")?.textContent).toBe(quotedText);
});

test("hides unapproved evaluation details from students", () => {
  render(
    <EvaluationResults
      evaluation={baseEvaluation}
      criteria={[criterion]}
      sourceText={sourceText}
      audience="student"
    />,
  );
  expect(screen.getByText(/Scores, comments, and evidence are hidden/i)).toBeInTheDocument();
  expect(screen.queryByText(criterionScore.ai_rationale)).not.toBeInTheDocument();
  expect(screen.queryByText(quotedText)).not.toBeInTheDocument();
});

test("reports failed evaluations without claiming faculty review is pending", () => {
  render(
    <EvaluationResults
      evaluation={{ ...baseEvaluation, status: "failed" }}
      criteria={[criterion]}
      audience="student"
    />,
  );
  expect(screen.getByText("Evaluation did not complete")).toBeInTheDocument();
  expect(screen.queryByText("Faculty review is required")).not.toBeInTheDocument();
});

test("faculty can save separate corrections, add notes, and approve", async () => {
  let evaluationState: Evaluation = baseEvaluation;
  const noteEvent: ReviewEvent = {
    id: "event-note",
    faculty_id: "faculty-1",
    criterion_score_id: null,
    action: "note_added",
    notes: "Clarify the evidence discussion.",
    created_at: "2026-01-03T01:00:00Z",
  };
  vi.mocked(appApi.evaluation).mockImplementation(async () => evaluationState);
  vi.mocked(appApi.updateCriterion).mockImplementation(
    async (_evaluationId, scoreId, updates) => {
      const currentScore = evaluationState.criterion_scores.find(
        (score) => score.id === scoreId,
      );
      if (!currentScore) {
        throw new Error("Missing criterion score fixture");
      }
      const updatedScore = {
        ...currentScore,
        faculty_score: updates.faculty_score,
        faculty_rationale: updates.faculty_rationale,
        faculty_strengths: updates.faculty_strengths,
        faculty_weaknesses: updates.faculty_weaknesses,
        faculty_suggestions: updates.faculty_suggestions,
      };
      evaluationState = {
        ...evaluationState,
        faculty_total_score: updates.faculty_score,
        criterion_scores: [updatedScore],
      };
      return updatedScore;
    },
  );
  vi.mocked(appApi.addReviewNote).mockImplementation(async () => {
    evaluationState = {
      ...evaluationState,
      review_history: [...evaluationState.review_history, noteEvent],
    };
    return noteEvent;
  });
  vi.mocked(appApi.reviewEvaluation).mockImplementation(async (_id, action, notes) => {
    const decisionEvent: ReviewEvent = {
      id: "event-approval",
      faculty_id: "faculty-1",
      criterion_score_id: null,
      action,
      notes: notes ?? null,
      created_at: "2026-01-03T02:00:00Z",
    };
    evaluationState = {
      ...evaluationState,
      status: action,
      review_history: [...evaluationState.review_history, decisionEvent],
    };
    return evaluationState;
  });

  renderFacultyReview();
  fireEvent.change(
    await screen.findByLabelText(/Faculty score \(AI: 2.0000\)/),
    { target: { value: "3.5" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save correction" }));

  await waitFor(() =>
    expect(appApi.updateCriterion).toHaveBeenCalledWith(
      baseEvaluation.id,
      criterionScore.id,
      expect.objectContaining({
        faculty_score: "3.5",
        faculty_rationale: null,
        faculty_strengths: [],
      }),
    ),
  );
  expect(
    await screen.findByText(criterionScore.ai_rationale),
  ).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Note"), {
    target: { value: "Clarify the evidence discussion." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add note" }));
  expect(await screen.findByText("Clarify the evidence discussion.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Approve" }));
  await waitFor(() =>
    expect(appApi.reviewEvaluation).toHaveBeenCalledWith(
      baseEvaluation.id,
      "approved",
      undefined,
    ),
  );
  expect(
    await screen.findByText(/No further review actions are available/),
  ).toBeInTheDocument();
  expect(screen.getAllByText("Faculty member faculty-1").length).toBeGreaterThan(0);
});
