import api from "./client";
import type {
  AccessTokenResponse,
  Course,
  CriterionScore,
  DemoEvaluation,
  Essay,
  EssayText,
  Evaluation,
  Enrollment,
  ReviewEvent,
  ReviewQueueItem,
  Rubric,
  RubricCriterionInput,
  RubricVersion,
  User,
} from "./types";

export interface RegistrationInput {
  full_name: string;
  email: string;
  password: string;
}

export interface EvaluationHistoryOptions {
  essayId?: string;
  limit?: number;
  offset?: number;
}

export const authApi = {
  async register(input: RegistrationInput): Promise<User> {
    const response = await api.post<User>("/auth/register", input);
    return response.data;
  },
  async login(input: Pick<RegistrationInput, "email" | "password">): Promise<AccessTokenResponse> {
    const response = await api.post<AccessTokenResponse>("/auth/login", input);
    return response.data;
  },
  async refresh(): Promise<AccessTokenResponse> {
    const response = await api.post<AccessTokenResponse>("/auth/refresh");
    return response.data;
  },
  async currentUser(): Promise<User> {
    const response = await api.get<User>("/auth/me");
    return response.data;
  },
  async logout(): Promise<void> {
    await api.post("/auth/logout");
  },
};

export const appApi = {
  async courses(): Promise<Course[]> {
    const response = await api.get<Course[]>("/courses");
    return response.data;
  },
  async availableCourses(): Promise<Course[]> {
    const response = await api.get<Course[]>("/courses/available");
    return response.data;
  },
  async enrollInCourse(courseId: string): Promise<Enrollment> {
    const response = await api.post<Enrollment>(
      `/courses/${courseId}/self-enrollment`,
    );
    return response.data;
  },
  async essays(): Promise<Essay[]> {
    const response = await api.get<Essay[]>("/essays");
    return response.data;
  },
  async essay(essayId: string): Promise<Essay> {
    const response = await api.get<Essay>(`/essays/${essayId}`);
    return response.data;
  },
  async essayText(essayId: string): Promise<EssayText> {
    const response = await api.get<EssayText>(`/essays/${essayId}/text`);
    return response.data;
  },
  async uploadEssay(file: File, courseId: string): Promise<Essay> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("course_id", courseId);
    const response = await api.post<Essay>("/essays", formData);
    return response.data;
  },
  async rubrics(): Promise<Rubric[]> {
    const response = await api.get<Rubric[]>("/rubrics");
    return response.data;
  },
  async createRubric(input: {
    course_id: string;
    title: string;
    description: string | null;
  }): Promise<Rubric> {
    const response = await api.post<Rubric>("/rubrics", input);
    return response.data;
  },
  async updateRubric(
    rubricId: string,
    updates: { title?: string; description?: string | null },
  ): Promise<Rubric> {
    const response = await api.patch<Rubric>(`/rubrics/${rubricId}`, updates);
    return response.data;
  },
  async rubricVersions(rubricId: string): Promise<RubricVersion[]> {
    const response = await api.get<RubricVersion[]>(
      `/rubrics/${rubricId}/versions`,
    );
    return response.data;
  },
  async createRubricVersion(rubricId: string): Promise<RubricVersion> {
    const response = await api.post<RubricVersion>(
      `/rubrics/${rubricId}/versions`,
    );
    return response.data;
  },
  async rubricVersion(versionId: string): Promise<RubricVersion> {
    const response = await api.get<RubricVersion>(
      `/rubric-versions/${versionId}`,
    );
    return response.data;
  },
  async replaceRubricCriteria(
    versionId: string,
    criteria: RubricCriterionInput[],
  ): Promise<RubricVersion> {
    const response = await api.put<RubricVersion>(
      `/rubric-versions/${versionId}/criteria`,
      { criteria },
    );
    return response.data;
  },
  async publishRubricVersion(versionId: string): Promise<RubricVersion> {
    const response = await api.post<RubricVersion>(
      `/rubric-versions/${versionId}/publish`,
    );
    return response.data;
  },
  async evaluations(options: EvaluationHistoryOptions = {}): Promise<Evaluation[]> {
    const response = await api.get<Evaluation[]>("/evaluations", {
      params: {
        essay_id: options.essayId,
        limit: options.limit ?? 50,
        offset: options.offset ?? 0,
      },
    });
    return response.data;
  },
  async evaluation(evaluationId: string): Promise<Evaluation> {
    const response = await api.get<Evaluation>(
      `/evaluations/${evaluationId}`,
    );
    return response.data;
  },
  async startEvaluation(
    essayId: string,
    rubricVersionId: string,
  ): Promise<Evaluation> {
    const response = await api.post<Evaluation>(
      `/essays/${essayId}/evaluations`,
      { rubric_version_id: rubricVersionId },
    );
    return response.data;
  },
  async reviewQueue(): Promise<ReviewQueueItem[]> {
    const response = await api.get<ReviewQueueItem[]>("/reviews/queue");
    return response.data;
  },
  async updateCriterion(
    evaluationId: string,
    scoreId: string,
    updates: {
      faculty_score: string | null;
      faculty_rationale: string | null;
      faculty_strengths: string[];
      faculty_weaknesses: string[];
      faculty_suggestions: string[];
    },
  ): Promise<CriterionScore> {
    const response = await api.patch<CriterionScore>(
      `/evaluations/${evaluationId}/criterion-scores/${scoreId}`,
      updates,
    );
    return response.data;
  },
  async addReviewNote(
    evaluationId: string,
    notes: string,
  ): Promise<ReviewEvent> {
    const response = await api.post<ReviewEvent>(
      `/evaluations/${evaluationId}/review-notes`,
      { notes },
    );
    return response.data;
  },
  async reviewEvaluation(
    evaluationId: string,
    action: "approved" | "rejected" | "changes_requested",
    notes?: string,
  ): Promise<Evaluation> {
    const response = await api.post<Evaluation>(
      `/evaluations/${evaluationId}/review`,
      { action, notes },
    );
    return response.data;
  },
};

export const demoApi = {
  async uploadEssay(file: File): Promise<DemoEvaluation> {
    const formData = new FormData();
    formData.append("file", file);
    const response = await api.post<DemoEvaluation>("/demo/evaluations", formData);
    return response.data;
  },
  async evaluations(): Promise<DemoEvaluation[]> {
    const response = await api.get<DemoEvaluation[]>("/demo/evaluations");
    return response.data;
  },
  async evaluation(evaluationId: string): Promise<DemoEvaluation> {
    const response = await api.get<DemoEvaluation>(
      `/demo/evaluations/${evaluationId}`,
    );
    return response.data;
  },
  async review(
    evaluationId: string,
    action: "approved" | "changes_requested",
    note?: string,
  ): Promise<DemoEvaluation> {
    const response = await api.post<DemoEvaluation>(
      `/demo/evaluations/${evaluationId}/review`,
      { action, note },
    );
    return response.data;
  },
};
