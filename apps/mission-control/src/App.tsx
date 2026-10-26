import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { MissionShell } from "./layouts/MissionShell";
import { AdminPage } from "./pages/AdminPage";
import { AgentProfilePage } from "./pages/AgentProfilePage";
import { AgentUniversePage } from "./pages/AgentUniversePage";
import { EvaluationLabPage } from "./pages/EvaluationLabPage";
import { FinOpsPage } from "./pages/FinOpsPage";
import { GovernancePage } from "./pages/GovernancePage";
import { LiveObservatoryPage } from "./pages/LiveObservatoryPage";
import { LoginPage } from "./pages/LoginPage";
import { MissionControlPage } from "./pages/MissionControlPage";
import { OnboardingStudioPage } from "./pages/OnboardingStudioPage";
import { ReleaseCommandPage } from "./pages/ReleaseCommandPage";
import { ReliabilityPage } from "./pages/ReliabilityPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";
import { WorkflowsPage } from "./pages/WorkflowsPage";
import { useAuth } from "./stores/auth";

function RequireAuth() {
  const { user, booted } = useAuth();
  if (!booted) {
    return (
      <div className="flex min-h-screen items-center justify-center text-[13px] text-[var(--ink-muted)]">
        Loading…
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<MissionShell />}>
          <Route index element={<MissionControlPage />} />
          <Route path="agents" element={<AgentUniversePage />} />
          <Route path="agents/:id" element={<AgentProfilePage />} />
          <Route path="onboarding" element={<OnboardingStudioPage />} />
          <Route path="workbench" element={<WorkbenchPage />} />
          <Route path="evaluations" element={<EvaluationLabPage />} />
          <Route path="releases" element={<ReleaseCommandPage />} />
          <Route path="observatory" element={<LiveObservatoryPage />} />
          <Route path="finops" element={<FinOpsPage />} />
          <Route path="governance" element={<GovernancePage />} />
          <Route path="reliability" element={<ReliabilityPage />} />
          <Route path="workflows" element={<WorkflowsPage />} />
          <Route path="admin" element={<AdminPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
