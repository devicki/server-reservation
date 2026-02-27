import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import DashboardPage from './pages/DashboardPage';
import FeedbackPage from './pages/FeedbackPage';
import GpuHealthPage from './pages/GpuHealthPage';
import ServersPage from './pages/ServersPage';
import UsersPage from './pages/UsersPage';
import SessionLogsPage from './pages/SessionLogsPage';
import ServeCasePage from './pages/ServeCasePage';
import ReleaseNotesPage from './pages/ReleaseNotesPage';

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="loading">Loading...</div>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="loading">Loading...</div>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (user.role !== 'admin') {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="loading">Loading...</div>;
  }

  if (user) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route
            path="/login"
            element={
              <PublicRoute>
                <LoginPage />
              </PublicRoute>
            }
          />
          <Route
            path="/register"
            element={
              <PublicRoute>
                <RegisterPage />
              </PublicRoute>
            }
          />
          <Route
            path="/"
            element={
              <PrivateRoute>
                <DashboardPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/gpu-health"
            element={
              <PrivateRoute>
                <GpuHealthPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/feedback"
            element={
              <PrivateRoute>
                <FeedbackPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/users"
            element={
              <AdminRoute>
                <UsersPage />
              </AdminRoute>
            }
          />
          <Route
            path="/servers"
            element={
              <AdminRoute>
                <ServersPage />
              </AdminRoute>
            }
          />
          <Route
            path="/serve-cases"
            element={
              <PrivateRoute>
                <ServeCasePage />
              </PrivateRoute>
            }
          />
          <Route
            path="/serve-cases/:id"
            element={
              <PrivateRoute>
                <ServeCasePage />
              </PrivateRoute>
            }
          />
          <Route
            path="/session-logs"
            element={
              <AdminRoute>
                <SessionLogsPage />
              </AdminRoute>
            }
          />
          <Route
            path="/release-notes"
            element={
              <PrivateRoute>
                <ReleaseNotesPage />
              </PrivateRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
