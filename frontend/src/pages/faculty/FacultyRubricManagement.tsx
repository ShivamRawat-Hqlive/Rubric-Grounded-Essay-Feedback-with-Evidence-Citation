import { useCallback, useEffect, useMemo, useState } from "react";
import { appApi } from "../../api/services";
import { getApiErrorMessage } from "../../api/client";
import type {
  Course,
  Rubric,
  RubricCriterion,
  RubricCriterionInput,
  RubricVersion,
} from "../../api/types";
import { EmptyState, ErrorAlert } from "../../components/ui/Feedback";

interface FacultyRubricManagementProps {
  courses: Course[];
}

interface CriterionDraft {
  name: string;
  description: string;
  weightPercent: string;
  minScore: string;
  maxScore: string;
  levels: { score: string; description: string }[];
}

const PERCENT_SCALE = 10_000;
const TOTAL_WEIGHT_UNITS = 100 * PERCENT_SCALE;

function emptyCriterion(): CriterionDraft {
  return {
    name: "",
    description: "",
    weightPercent: "100",
    minScore: "0",
    maxScore: "4",
    levels: [],
  };
}

function weightUnitsFromPercent(value: string): number | null {
  const match = /^(\d{1,3})(?:\.(\d{1,4}))?$/.exec(value.trim());
  if (!match) {
    return null;
  }
  const fractional = (match[2] ?? "").padEnd(4, "0");
  const units = Number(match[1]) * PERCENT_SCALE + Number(fractional || "0");
  return units > 0 && units <= TOTAL_WEIGHT_UNITS ? units : null;
}

function percentFromWeight(weight: string): string {
  const match = /^(\d+)(?:\.(\d{1,6}))?$/.exec(weight);
  if (!match) {
    return "";
  }
  const units = Number(match[1]) * 1_000_000 +
    Number((match[2] ?? "").padEnd(6, "0") || "0");
  const whole = Math.floor(units / PERCENT_SCALE);
  const fraction = String(units % PERCENT_SCALE).padStart(4, "0").replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : String(whole);
}

function weightFromUnits(units: number): string {
  const whole = Math.floor(units / 1_000_000);
  const fraction = String(units % 1_000_000).padStart(6, "0");
  return `${whole}.${fraction}`;
}

function criterionDrafts(criteria: RubricCriterion[]): CriterionDraft[] {
  return criteria.map((criterion) => ({
    name: criterion.name,
    description: criterion.description,
    weightPercent: percentFromWeight(criterion.weight),
    minScore: criterion.min_score,
    maxScore: criterion.max_score,
    levels: criterion.levels.map((level) => ({
      score: level.score,
      description: level.description,
    })),
  }));
}

function validateDraft(
  title: string,
  criteria: CriterionDraft[],
): { payload: RubricCriterionInput[]; error: string } {
  if (!title.trim()) {
    return { payload: [], error: "Enter a rubric title." };
  }
  if (title.trim().length > 200) {
    return { payload: [], error: "The rubric title must be 200 characters or fewer." };
  }
  if (criteria.length === 0) {
    return { payload: [], error: "Add at least one criterion." };
  }

  const names = new Set<string>();
  const payload: RubricCriterionInput[] = [];
  let totalWeightUnits = 0;
  for (const [index, criterion] of criteria.entries()) {
    const name = criterion.name.trim();
    const description = criterion.description.trim();
    if (!name || name.length > 120 || !description || description.length > 5000) {
      return {
        payload: [],
        error: `Complete criterion ${index + 1}; names are limited to 120 characters and descriptions to 5,000.`,
      };
    }
    if (names.has(name.toLocaleLowerCase())) {
      return { payload: [], error: "Criterion names must be unique." };
    }
    names.add(name.toLocaleLowerCase());

    const weightUnits = weightUnitsFromPercent(criterion.weightPercent);
    if (weightUnits === null) {
      return {
        payload: [],
        error: `Criterion ${index + 1} needs a weight greater than 0 and at most 100%, with up to 4 decimal places.`,
      };
    }
    totalWeightUnits += weightUnits;

    if (!/^-?\d+(?:\.\d{1,4})?$/.test(criterion.minScore) ||
      !/^-?\d+(?:\.\d{1,4})?$/.test(criterion.maxScore) ||
      !Number.isFinite(Number(criterion.minScore)) ||
      !Number.isFinite(Number(criterion.maxScore)) ||
      Number(criterion.maxScore) <= 0 ||
      Number(criterion.minScore) >= Number(criterion.maxScore)) {
      return {
        payload: [],
        error: `Criterion ${index + 1} needs a maximum score greater than its minimum, with up to 4 decimal places.`,
      };
    }
    if (criterion.levels.some(
      (level) =>
        Number(level.score) < Number(criterion.minScore) ||
        Number(level.score) > Number(criterion.maxScore),
    )) {
      return {
        payload: [],
        error: `Criterion ${index + 1} has score-level descriptors outside its score range.`,
      };
    }
    payload.push({
      name,
      description,
      levels: criterion.levels,
      min_score: criterion.minScore,
      max_score: criterion.maxScore,
      weight: weightFromUnits(weightUnits),
      sort_order: index,
    });
  }

  if (totalWeightUnits !== TOTAL_WEIGHT_UNITS) {
    return {
      payload: [],
      error: `Criterion weights must total exactly 100%. Current total: ${(totalWeightUnits / PERCENT_SCALE).toFixed(4).replace(/\.?0+$/, "")}%.`,
    };
  }
  return { payload, error: "" };
}

export function FacultyRubricManagement({
  courses,
}: FacultyRubricManagementProps) {
  const [rubrics, setRubrics] = useState<Rubric[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState(
    courses.find((course) => course.code === "ENG-101")?.id ?? courses[0]?.id ?? "",
  );
  const [selectedRubricId, setSelectedRubricId] = useState("");
  const [versions, setVersions] = useState<RubricVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [criteria, setCriteria] = useState<CriterionDraft[]>([]);
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selectedRubric = rubrics.find((rubric) => rubric.id === selectedRubricId);
  const selectedVersion = versions.find((version) => version.id === selectedVersionId);
  const courseRubrics = useMemo(
    () => rubrics.filter((rubric) => rubric.course_id === selectedCourseId),
    [rubrics, selectedCourseId],
  );
  const editable = creating || Boolean(
    selectedRubric &&
    selectedVersion &&
    !selectedVersion.is_published &&
    selectedRubric.status !== "archived",
  );
  const canEditMetadata = creating || selectedRubric?.status === "draft";

  const refreshRubrics = useCallback(async () => {
    const result = await appApi.rubrics();
    setRubrics(result);
    return result;
  }, []);

  useEffect(() => {
    let active = true;
    void appApi.rubrics()
      .then((result) => {
        if (active) {
          setRubrics(result);
        }
      })
      .catch((requestError: unknown) => {
        if (active) {
          setError(getApiErrorMessage(requestError, "Unable to load rubrics."));
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (courses.some((course) => course.id === selectedCourseId)) {
      return;
    }
    setSelectedCourseId(
      courses.find((course) => course.code === "ENG-101")?.id ?? courses[0]?.id ?? "",
    );
  }, [courses, selectedCourseId]);

  function resetEditor() {
    setSelectedRubricId("");
    setVersions([]);
    setSelectedVersionId("");
    setTitle("");
    setDescription("");
    setCriteria([]);
    setCreating(false);
  }

  async function selectRubric(rubricId: string) {
    setError("");
    setNotice("");
    setSelectedRubricId(rubricId);
    setCreating(false);
    setSelectedVersionId("");
    setVersions([]);
    if (!rubricId) {
      setTitle("");
      setDescription("");
      setCriteria([]);
      return;
    }

    const rubric = rubrics.find((item) => item.id === rubricId);
    if (!rubric) {
      return;
    }
    setTitle(rubric.title);
    setDescription(rubric.description ?? "");
    setBusy(true);
    try {
      const versionList = await appApi.rubricVersions(rubricId);
      setVersions(versionList);
      const currentVersion = [...versionList].reverse().find((item) => !item.is_published)
        ?? versionList[versionList.length - 1];
      setSelectedVersionId(currentVersion?.id ?? "");
      setCriteria(currentVersion ? criterionDrafts(currentVersion.criteria) : []);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load rubric versions."));
    } finally {
      setBusy(false);
    }
  }

  function startNewRubric() {
    resetEditor();
    setCreating(true);
    setTitle("");
    setDescription("");
    setCriteria([emptyCriterion()]);
    setError("");
    setNotice("");
  }

  async function startNewVersion() {
    if (!selectedRubric) {
      return;
    }
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const created = await appApi.createRubricVersion(selectedRubric.id);
      const versionList = await appApi.rubricVersions(selectedRubric.id);
      setVersions(versionList);
      setSelectedVersionId(created.id);
      setCriteria(criterionDrafts(created.criteria));
      setNotice(`Draft version ${created.version_number} created.`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to create a draft version."));
    } finally {
      setBusy(false);
    }
  }

  async function saveDraft(): Promise<{ rubricId: string; versionId: string } | null> {
    setError("");
    setNotice("");
    const validation = validateDraft(title, criteria);
    if (validation.error) {
      setError(validation.error);
      return null;
    }
    if (!selectedCourseId) {
      setError("Select an assigned course.");
      return null;
    }

    setBusy(true);
    try {
      let rubricId = selectedRubricId;
      let versionId = selectedVersionId;
      let rubric = selectedRubric;

      if (creating) {
        const createdRubric = await appApi.createRubric({
          course_id: selectedCourseId,
          title: title.trim(),
          description: description.trim() || null,
        });
        rubricId = createdRubric.id;
        rubric = createdRubric;
        setSelectedRubricId(rubricId);
        setCreating(false);
        setRubrics((current) => [createdRubric, ...current]);

        const createdVersions = await appApi.rubricVersions(rubricId);
        setVersions(createdVersions);
        const draftVersion = [...createdVersions].reverse().find((item) => !item.is_published);
        versionId = draftVersion?.id ?? "";
        setSelectedVersionId(versionId);
      } else if (rubric && rubric.status === "draft") {
        const updatedRubric = await appApi.updateRubric(rubric.id, {
          title: title.trim(),
          description: description.trim() || null,
        });
        rubric = updatedRubric;
        setRubrics((current) =>
          current.map((item) => item.id === updatedRubric.id ? updatedRubric : item),
        );
      }

      const targetVersion = versions.find((version) => version.id === versionId);
      const versionIsPublished = targetVersion?.is_published ?? false;
      if (!versionId || versionIsPublished || rubric?.status === "archived") {
        setError("Select an editable draft version before saving.");
        return null;
      }

      await appApi.replaceRubricCriteria(versionId, validation.payload);
      const updatedVersions = await appApi.rubricVersions(rubricId);
      setVersions(updatedVersions);
      setSelectedVersionId(versionId);
      await refreshRubrics();
      setNotice("Draft saved.");
      return { rubricId, versionId };
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to save the rubric draft."));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function publishDraft() {
    if (!editable) {
      setError("Select an editable draft version before publishing.");
      return;
    }
    const saved = await saveDraft();
    if (!saved) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await appApi.publishRubricVersion(saved.versionId);
      const [updatedRubrics, updatedVersions] = await Promise.all([
        refreshRubrics(),
        appApi.rubricVersions(saved.rubricId),
      ]);
      setVersions(updatedVersions);
      setSelectedRubricId(saved.rubricId);
      setSelectedVersionId(saved.versionId);
      const updatedRubric = updatedRubrics.find((item) => item.id === saved.rubricId);
      if (updatedRubric) {
        setTitle(updatedRubric.title);
      }
      setNotice("Rubric version published.");
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to publish this rubric version."));
    } finally {
      setBusy(false);
    }
  }

  function updateCriterion(index: number, updates: Partial<CriterionDraft>) {
    setCriteria((current) =>
      current.map((criterion, itemIndex) =>
        itemIndex === index ? { ...criterion, ...updates } : criterion,
      ),
    );
  }

  const totalWeight = criteria.reduce(
    (total, criterion) => total + (weightUnitsFromPercent(criterion.weightPercent) ?? 0),
    0,
  );

  return (
    <section className="space-y-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-navy-900">Manage Rubrics</h3>
          <p className="mt-1 text-sm text-slate-500">
            Create course rubrics, edit drafts, and publish versioned criteria.
          </p>
        </div>
        <button
          type="button"
          onClick={startNewRubric}
          disabled={courses.length === 0 || busy}
          className="rounded-lg bg-navy-800 px-4 py-2.5 text-sm font-semibold text-white hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
        >
          New rubric
        </button>
      </header>

      {error && <ErrorAlert message={error} />}
      {notice && (
        <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
          {notice}
        </p>
      )}

      {courses.length === 0 ? (
        <EmptyState title="No assigned courses">
          Rubrics can only be managed for courses where you are assigned as faculty.
        </EmptyState>
      ) : (
        <>
          <label className="block max-w-xl text-sm font-medium text-slate-700">
            Assigned course
            <select
              aria-label="Assigned course"
              value={selectedCourseId}
              disabled={busy}
              onChange={(event) => {
                setSelectedCourseId(event.target.value);
                resetEditor();
                setError("");
                setNotice("");
              }}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5"
            >
              {courses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.code} — {course.name}
                </option>
              ))}
            </select>
          </label>

          <div className="grid gap-5 lg:grid-cols-[minmax(240px,0.75fr)_minmax(0,1.25fr)]">
            <div className="space-y-3">
              <h4 className="font-semibold text-slate-800">Rubrics for this course</h4>
              {loading ? (
                <p className="text-sm text-slate-500">Loading rubrics…</p>
              ) : courseRubrics.length === 0 ? (
                <EmptyState title="No rubrics yet">
                  Create a rubric to start a draft for this course.
                </EmptyState>
              ) : (
                <div className="space-y-2">
                  {courseRubrics.map((rubric) => (
                    <button
                      type="button"
                      key={rubric.id}
                      aria-pressed={selectedRubricId === rubric.id}
                      onClick={() => void selectRubric(rubric.id)}
                      className={`w-full rounded-lg border p-3 text-left ${
                        selectedRubricId === rubric.id
                          ? "border-indigo-500 bg-indigo-50"
                          : "border-slate-200 hover:bg-slate-50"
                      }`}
                    >
                      <span className="block font-medium text-slate-900">{rubric.title}</span>
                      <span className="mt-1 block text-xs capitalize text-slate-500">
                        {rubric.status}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-4">
              {creating || selectedRubric ? (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block text-sm font-medium text-slate-700">
                      Rubric title
                      <input
                        aria-label="Rubric title"
                        value={title}
                        maxLength={200}
                        disabled={!canEditMetadata || busy}
                        onChange={(event) => setTitle(event.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                      />
                    </label>
                    <label className="block text-sm font-medium text-slate-700">
                      Description
                      <input
                        aria-label="Rubric description"
                        value={description}
                        maxLength={5000}
                        disabled={!canEditMetadata || busy}
                        onChange={(event) => setDescription(event.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                      />
                    </label>
                  </div>

                  {versions.length > 0 && (
                    <div className="space-y-2">
                      <label className="block text-sm font-medium text-slate-700">
                        Rubric version
                        <select
                          aria-label="Rubric version"
                          value={selectedVersionId}
                          disabled={busy}
                          onChange={(event) => {
                            const version = versions.find((item) => item.id === event.target.value);
                            setSelectedVersionId(event.target.value);
                            setCriteria(version ? criterionDrafts(version.criteria) : []);
                          }}
                          className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2"
                        >
                          {versions.map((version) => (
                            <option key={version.id} value={version.id}>
                              v{version.version_number} · {version.is_published ? "Published" : "Draft"}
                            </option>
                          ))}
                        </select>
                      </label>
                      {selectedRubric?.status === "published" &&
                        versions.every((version) => version.is_published) && (
                          <button
                            type="button"
                            onClick={() => void startNewVersion()}
                            disabled={busy}
                            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                          >
                            Create next draft version
                          </button>
                        )}
                    </div>
                  )}

                  {editable ? (
                    <div className="space-y-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h4 className="font-semibold text-slate-800">Criteria</h4>
                        <p
                          className={`text-sm font-semibold ${
                            totalWeight === TOTAL_WEIGHT_UNITS
                              ? "text-emerald-700"
                              : "text-amber-800"
                          }`}
                        >
                          Total weight: {(totalWeight / PERCENT_SCALE).toFixed(4).replace(/\.?0+$/, "")}%
                        </p>
                      </div>
                      {criteria.map((criterion, index) => (
                        <fieldset
                          key={index}
                          className="space-y-3 rounded-lg border border-slate-200 p-4"
                        >
                          <legend className="px-1 text-sm font-semibold text-slate-700">
                            Criterion {index + 1}
                          </legend>
                          <div className="grid gap-3 sm:grid-cols-2">
                            <label className="text-sm font-medium text-slate-700">
                              Name
                              <input
                                aria-label={`Criterion ${index + 1} name`}
                                value={criterion.name}
                                maxLength={120}
                                onChange={(event) => updateCriterion(index, { name: event.target.value })}
                                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                              />
                            </label>
                            <label className="text-sm font-medium text-slate-700">
                              Weight (%)
                              <input
                                aria-label={`Criterion ${index + 1} weight`}
                                type="number"
                                min="0.0001"
                                max="100"
                                step="0.0001"
                                value={criterion.weightPercent}
                                onChange={(event) => updateCriterion(index, { weightPercent: event.target.value })}
                                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                              />
                            </label>
                            <label className="text-sm font-medium text-slate-700">
                              Maximum score
                              <input
                                aria-label={`Criterion ${index + 1} maximum score`}
                                type="number"
                                min="0.0001"
                                step="0.0001"
                                value={criterion.maxScore}
                                onChange={(event) => updateCriterion(index, { maxScore: event.target.value })}
                                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                              />
                            </label>
                          </div>
                          <label className="block text-sm font-medium text-slate-700">
                            Description
                            <textarea
                              aria-label={`Criterion ${index + 1} description`}
                              value={criterion.description}
                              maxLength={5000}
                              rows={2}
                              onChange={(event) => updateCriterion(index, { description: event.target.value })}
                              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                            />
                          </label>
                          <button
                            type="button"
                            onClick={() => setCriteria((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                            className="text-sm font-semibold text-rose-700 hover:underline"
                          >
                            Remove criterion
                          </button>
                        </fieldset>
                      ))}
                      <button
                        type="button"
                        onClick={() => setCriteria((current) => [...current, {
                          ...emptyCriterion(),
                          weightPercent: "",
                        }])}
                        className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        Add criterion
                      </button>
                      <div className="flex flex-wrap gap-3">
                        <button
                          type="button"
                          onClick={() => void saveDraft()}
                          disabled={busy}
                          className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                        >
                          {busy ? "Saving…" : "Save draft"}
                        </button>
                        <button
                          type="button"
                          onClick={() => void publishDraft()}
                          disabled={busy}
                          className="rounded-lg bg-indigo-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-800 disabled:opacity-60"
                        >
                          Publish version
                        </button>
                      </div>
                    </div>
                  ) : (
                    <EmptyState title={selectedRubric?.status === "archived" ? "Rubric archived" : "Published version"}>
                      {selectedRubric?.status === "archived"
                        ? "Archived rubrics cannot be edited or receive new versions."
                        : "Published versions are immutable. Create the next draft version to make changes."}
                    </EmptyState>
                  )}
                </>
              ) : (
                <EmptyState title="Select a rubric or create one">
                  Choose a rubric in this course to view its versions and edit an unpublished draft.
                </EmptyState>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
