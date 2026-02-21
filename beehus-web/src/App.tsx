import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import ProtectedRoute from "./components/ProtectedRoute";
import { AuthProvider } from "./context/AuthContext";
import { ToastProvider } from "./context/ToastContext";

// Lazy-loaded pages — each page is code-split into its own chunk,
// so the initial bundle only loads what the user actually visits.
const Login = lazy(() => import("./pages/Login"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const LiveView = lazy(() => import("./pages/LiveView"));
const Workspaces = lazy(() => import("./pages/Workspaces"));
const Jobs = lazy(() => import("./pages/Jobs"));
const Runs = lazy(() => import("./pages/Runs"));
const Credentials = lazy(() => import("./pages/Credentials"));
const Users = lazy(() => import("./pages/Users"));
const AcceptInvitation = lazy(() => import("./pages/AcceptInvitation"));
const ForgotPassword = lazy(() => import("./pages/ForgotPassword"));
const ResetPassword = lazy(() => import("./pages/ResetPassword"));
const UserProfile = lazy(() => import("./pages/UserProfile"));
const Downloads = lazy(() => import("./pages/Downloads"));

function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <BrowserRouter>
          <Suspense
            fallback={
              <div className="flex items-center justify-center h-screen bg-slate-900 text-slate-400">
                Loading…
              </div>
            }
          >
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/accept-invitation" element={<AcceptInvitation />} />
              <Route path="/forgot-password" element={<ForgotPassword />} />
              <Route path="/reset-password" element={<ResetPassword />} />

              {/* Protected Routes */}
              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <Dashboard />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/workspaces"
                element={
                  <ProtectedRoute>
                    <Workspaces />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/jobs"
                element={
                  <ProtectedRoute>
                    <Jobs />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/runs"
                element={
                  <ProtectedRoute>
                    <Runs />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/live/:runId"
                element={
                  <ProtectedRoute>
                    <LiveView />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/credentials"
                element={
                  <ProtectedRoute>
                    <Credentials />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/users"
                element={
                  <ProtectedRoute requireAdmin>
                    <Users />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/profile"
                element={
                  <ProtectedRoute>
                    <UserProfile />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/downloads"
                element={
                  <ProtectedRoute>
                    <Downloads />
                  </ProtectedRoute>
                }
              />

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </ToastProvider>
    </AuthProvider>
  );
}

export default App;
