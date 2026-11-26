import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { DemoEvaluationPage } from "./pages/demo/DemoEvaluationPage";
import { DemoFacultyPage } from "./pages/demo/DemoFacultyPage";
import { DemoSubmissionPage } from "./pages/demo/DemoSubmissionPage";
import { HomePage } from "./pages/HomePage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/student" element={<DemoSubmissionPage />} />
        <Route
          path="/student/essays/:essayId"
          element={<DemoEvaluationPage />}
        />
        <Route path="/faculty" element={<DemoFacultyPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
