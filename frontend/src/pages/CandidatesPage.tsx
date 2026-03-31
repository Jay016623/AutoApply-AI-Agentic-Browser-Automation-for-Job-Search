import { useMemo, useState } from 'react';
import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Grid from '@mui/material/Grid';
import Chip from '@mui/material/Chip';

import ErrorBoundary from '@/components/common/ErrorBoundary';
import LoadingState from '@/components/common/LoadingState';
import { useCandidate, useCandidates } from '@/hooks/useCandidates';

function CandidatesPage() {
  const { data, isLoading } = useCandidates();
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const { data: selected, isLoading: detailLoading } = useCandidate(selectedId);

  const candidates = useMemo(() => data?.items ?? [], [data]);

  if (isLoading) {
    return <LoadingState message="Loading candidates..." />;
  }

  return (
    <ErrorBoundary>
      <Box>
        <Typography variant="h4" gutterBottom>
          Candidates
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
          Candidate-centric profiles and versioned document history foundation.
        </Typography>

        <Grid container spacing={3}>
          <Grid item xs={12} md={4}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Candidate List
                </Typography>
                <List>
                  {candidates.map((candidate) => (
                    <ListItemButton
                      key={candidate.id}
                      selected={selectedId === candidate.id}
                      onClick={() => setSelectedId(candidate.id)}
                    >
                      <ListItemText
                        primary={candidate.full_name}
                        secondary={candidate.email}
                      />
                    </ListItemButton>
                  ))}
                </List>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={8}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Candidate Detail
                </Typography>
                {!selectedId ? (
                  <Typography variant="body2" color="text.secondary">
                    Select a candidate to view details.
                  </Typography>
                ) : detailLoading ? (
                  <LoadingState message="Loading candidate detail..." />
                ) : selected ? (
                  <>
                    <Typography variant="subtitle1">{selected.full_name}</Typography>
                    <Typography variant="body2" color="text.secondary">{selected.email}</Typography>
                    <Box sx={{ mt: 2, display: 'flex', gap: 1 }}>
                      <Chip
                        size="small"
                        label={selected.is_active ? 'Active' : 'Inactive'}
                        color={selected.is_active ? 'success' : 'default'}
                      />
                      {selected.is_default && <Chip size="small" label="Default" color="primary" />}
                    </Box>
                  </>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    Candidate not found.
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Box>
    </ErrorBoundary>
  );
}

export default CandidatesPage;
