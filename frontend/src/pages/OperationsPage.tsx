import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Grid from '@mui/material/Grid';
import Paper from '@mui/material/Paper';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import Typography from '@mui/material/Typography';

import LoadingState from '@/components/common/LoadingState';
import { useManualQueue, useRetryQueue } from '@/hooks/useExecution';
import { useAppStore } from '@/store/useAppStore';
import { canAccess } from '@/services/authz';

function OperationsPage() {
  const [tab, setTab] = useState(0);
  const role = useAppStore((s) => s.authRole);
  const { data: manualQueue, isLoading: manualLoading, isError: manualError } = useManualQueue();
  const { data: retryQueue, isLoading: retryLoading, isError: retryError } = useRetryQueue();

  if (!canAccess(role, 'operator')) {
    return <Alert severity="warning">Operator role is required for review queue visibility.</Alert>;
  }

  const loading = manualLoading || retryLoading;

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Operations Queue
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Monitor manual checkpoints and retry backlog for the current tenant.
      </Typography>

      <Tabs value={tab} onChange={(_, value) => setTab(value)} sx={{ mb: 2 }}>
        <Tab label={`Manual Review (${manualQueue?.total ?? 0})`} />
        <Tab label={`Retry Queue (${retryQueue?.total ?? 0})`} />
      </Tabs>

      {loading && <LoadingState message="Loading operator queues..." />}
      {(manualError || retryError) && <Alert severity="error">Failed to load operator queue data.</Alert>}

      {!loading && !manualError && !retryError && (
        <Grid container spacing={2}>
          {(tab === 0 ? manualQueue?.items : retryQueue?.items)?.map((attempt) => (
            <Grid item xs={12} md={6} key={attempt.id}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  Attempt {attempt.id}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Application: {attempt.application_id}
                </Typography>
                <Chip size="small" label={attempt.status} sx={{ mr: 1 }} />
                {attempt.manual_checkpoint_required && (
                  <Chip size="small" color="warning" label="Manual checkpoint" />
                )}
                {attempt.manual_checkpoint_reason && (
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    Reason: {attempt.manual_checkpoint_reason}
                  </Typography>
                )}
                {attempt.last_error_code && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                    Last error: {attempt.last_error_code}
                  </Typography>
                )}
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}

export default OperationsPage;
