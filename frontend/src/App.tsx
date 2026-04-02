import { Routes, Route, Navigate } from 'react-router-dom';
import Snackbar from '@mui/material/Snackbar';
import Alert from '@mui/material/Alert';

import AppLayout from '@/components/layout/AppLayout';
import DashboardPage from '@/pages/DashboardPage';
import JobSearchPage from '@/pages/JobSearchPage';
import ApplicationsPage from '@/pages/ApplicationsPage';
import CandidatesPage from '@/pages/CandidatesPage';
import ResumesPage from '@/pages/ResumesPage';
import SettingsPage from '@/pages/SettingsPage';
import AnalyticsPage from '@/pages/AnalyticsPage';
import OperationsPage from '@/pages/OperationsPage';
import { useAppStore } from '@/store/useAppStore';
import { useSessionBootstrap } from '@/hooks/useSession';
import LoadingState from '@/components/common/LoadingState';

function App() {
  const notification = useAppStore((s) => s.notification);
  const clearNotification = useAppStore((s) => s.clearNotification);
  const sessionBootstrapped = useAppStore((s) => s.sessionBootstrapped);
  useSessionBootstrap();

  if (!sessionBootstrapped) {
    return <LoadingState message="Initializing secure tenant session..." />;
  }

  return (
    <>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/jobs" element={<JobSearchPage />} />
          <Route path="/candidates" element={<CandidatesPage />} />
          <Route path="/applications" element={<ApplicationsPage />} />
          <Route path="/resumes" element={<ResumesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/operations" element={<OperationsPage />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>

      <Snackbar
        open={!!notification}
        autoHideDuration={5000}
        onClose={clearNotification}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        {notification ? (
          <Alert
            onClose={clearNotification}
            severity={notification.severity}
            variant="filled"
            sx={{ width: '100%' }}
          >
            {notification.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </>
  );
}

export default App;
