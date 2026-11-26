import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { appApi } from "../../api/services";
import type { Course, Rubric, RubricVersion } from "../../api/types";
import { FacultyRubricManagement } from "./FacultyRubricManagement";

vi.mock("../../api/services", () => ({
  appApi: {
    rubrics: vi.fn(),
    rubricVersions: vi.fn(),
    createRubric: vi.fn(),
    updateRubric: vi.fn(),
    createRubricVersion: vi.fn(),
    replaceRubricCriteria: vi.fn(),
    publishRubricVersion: vi.fn(),
  },
}));

const course: Course = {
  id: "eng-course",
  name: "English Composition",
  code: "ENG-101",
  created_by_id: "faculty-1",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const rubric: Rubric = {
  id: "rubric-1",
  course_id: course.id,
  created_by_id: "faculty-1",
  title: "Composition rubric",
  description: "Writing criteria",
  status: "draft",
  created_at: "2026-01-02T00:00:00Z",
};

const draftVersion: RubricVersion = {
  id: "version-1",
  rubric_id: rubric.id,
  version_number: 1,
  is_published: false,
  published_at: null,
  snapshot: null,
  criteria: [],
};

const publishedVersion: RubricVersion = {
  ...draftVersion,
  is_published: true,
  published_at: "2026-01-03T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(appApi.rubrics).mockResolvedValue([]);
  vi.mocked(appApi.rubricVersions).mockResolvedValue([draftVersion]);
  vi.mocked(appApi.createRubric).mockResolvedValue(rubric);
  vi.mocked(appApi.updateRubric).mockResolvedValue(rubric);
  vi.mocked(appApi.replaceRubricCriteria).mockResolvedValue(draftVersion);
  vi.mocked(appApi.publishRubricVersion).mockResolvedValue(publishedVersion);
});

test("creates and publishes a rubric for the assigned ENG-101 course", async () => {
  vi.mocked(appApi.rubrics)
    .mockResolvedValueOnce([])
    .mockResolvedValue([rubric]);
  vi.mocked(appApi.rubricVersions)
    .mockResolvedValueOnce([draftVersion])
    .mockResolvedValueOnce([draftVersion])
    .mockResolvedValueOnce([publishedVersion]);
  render(<FacultyRubricManagement courses={[course]} />);

  expect(await screen.findByLabelText("Assigned course")).toHaveValue(course.id);
  expect(screen.getByRole("option", { name: /ENG-101/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "New rubric" }));
  fireEvent.change(screen.getByLabelText("Rubric title"), {
    target: { value: "Composition rubric" },
  });
  fireEvent.change(screen.getByLabelText("Criterion 1 name"), {
    target: { value: "Thesis" },
  });
  fireEvent.change(screen.getByLabelText("Criterion 1 description"), {
    target: { value: "Presents a focused claim." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add criterion" }));
  fireEvent.change(screen.getByLabelText("Criterion 2 name"), {
    target: { value: "Evidence" },
  });
  fireEvent.change(screen.getByLabelText("Criterion 2 description"), {
    target: { value: "Supports ideas with evidence." },
  });
  fireEvent.change(screen.getByLabelText("Criterion 1 weight"), {
    target: { value: "60" },
  });
  fireEvent.change(screen.getByLabelText("Criterion 2 weight"), {
    target: { value: "40" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Publish version" }));

  await waitFor(() =>
    expect(appApi.createRubric).toHaveBeenCalledWith({
      course_id: course.id,
      title: "Composition rubric",
      description: null,
    }),
  );
  await waitFor(() =>
    expect(appApi.replaceRubricCriteria).toHaveBeenCalledWith(
      draftVersion.id,
      [
        expect.objectContaining({
          name: "Thesis",
          weight: "0.600000",
          max_score: "4",
          sort_order: 0,
        }),
        expect.objectContaining({
          name: "Evidence",
          weight: "0.400000",
          max_score: "4",
          sort_order: 1,
        }),
      ],
    ),
  );
  expect(appApi.publishRubricVersion).toHaveBeenCalledWith(draftVersion.id);
  expect(await screen.findByRole("status")).toHaveTextContent("Rubric version published.");
});

test("rejects criterion weights that do not total exactly 100 percent", async () => {
  render(<FacultyRubricManagement courses={[course]} />);
  await screen.findByLabelText("Assigned course");
  fireEvent.click(screen.getByRole("button", { name: "New rubric" }));
  fireEvent.change(screen.getByLabelText("Rubric title"), {
    target: { value: "Uneven rubric" },
  });
  fireEvent.change(screen.getByLabelText("Criterion 1 name"), {
    target: { value: "Thesis" },
  });
  fireEvent.change(screen.getByLabelText("Criterion 1 description"), {
    target: { value: "A thesis criterion." },
  });
  fireEvent.change(screen.getByLabelText("Criterion 1 weight"), {
    target: { value: "60" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add criterion" }));
  fireEvent.change(screen.getByLabelText("Criterion 2 name"), {
    target: { value: "Evidence" },
  });
  fireEvent.change(screen.getByLabelText("Criterion 2 description"), {
    target: { value: "An evidence criterion." },
  });
  fireEvent.change(screen.getByLabelText("Criterion 2 weight"), {
    target: { value: "39" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Criterion weights must total exactly 100%",
  );
  expect(appApi.createRubric).not.toHaveBeenCalled();
});

test("lists published and draft versions and permits starting a new version", async () => {
  const publishedRubric = { ...rubric, status: "published" as const };
  const nextDraft: RubricVersion = {
    ...draftVersion,
    id: "version-2",
    version_number: 2,
  };
  vi.mocked(appApi.rubrics).mockResolvedValue([publishedRubric]);
  vi.mocked(appApi.rubricVersions)
    .mockResolvedValueOnce([publishedVersion])
    .mockResolvedValue([publishedVersion, nextDraft]);
  vi.mocked(appApi.createRubricVersion).mockResolvedValue(nextDraft);
  render(<FacultyRubricManagement courses={[course]} />);

  fireEvent.click(await screen.findByRole("button", { name: /Composition rubric/ }));

  expect(await screen.findByRole("option", { name: "v1 · Published" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Create next draft version" }));
  await waitFor(() =>
    expect(appApi.createRubricVersion).toHaveBeenCalledWith(rubric.id),
  );
  expect(await screen.findByRole("option", { name: "v2 · Draft" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Create next draft version" })).not.toBeInTheDocument();
});

test("edits and saves an existing draft rubric and its criteria", async () => {
  const existingCriterion = {
    id: "criterion-1",
    rubric_version_id: draftVersion.id,
    name: "Thesis",
    description: "Presents a focused claim.",
    levels: [],
    min_score: "0",
    max_score: "4",
    weight: "1.000000",
    sort_order: 0,
  };
  const populatedDraft = {
    ...draftVersion,
    criteria: [existingCriterion],
  };
  vi.mocked(appApi.rubrics).mockResolvedValue([rubric]);
  vi.mocked(appApi.rubricVersions).mockResolvedValue([populatedDraft]);
  vi.mocked(appApi.updateRubric).mockResolvedValue({
    ...rubric,
    title: "Revised composition rubric",
  });
  render(<FacultyRubricManagement courses={[course]} />);

  fireEvent.click(await screen.findByRole("button", { name: /Composition rubric/ }));
  fireEvent.change(await screen.findByLabelText("Rubric title"), {
    target: { value: "Revised composition rubric" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

  await waitFor(() =>
    expect(appApi.updateRubric).toHaveBeenCalledWith(rubric.id, {
      title: "Revised composition rubric",
      description: "Writing criteria",
    }),
  );
  expect(appApi.replaceRubricCriteria).toHaveBeenCalledWith(
    draftVersion.id,
    [
      expect.objectContaining({
        name: "Thesis",
        weight: "1.000000",
        max_score: "4",
      }),
    ],
  );
});
