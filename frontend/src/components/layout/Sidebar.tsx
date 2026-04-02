import { useLocation, useNavigate } from 'react-router-dom';
import Box from '@mui/material/Box';
import Drawer from '@mui/material/Drawer';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import Divider from '@mui/material/Divider';
import DashboardIcon from '@mui/icons-material/Dashboard';
import WorkIcon from '@mui/icons-material/Work';
import PeopleIcon from '@mui/icons-material/People';
import SendIcon from '@mui/icons-material/Send';
import DescriptionIcon from '@mui/icons-material/Description';
import BarChartIcon from '@mui/icons-material/BarChart';
import SettingsIcon from '@mui/icons-material/Settings';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import FactCheckIcon from '@mui/icons-material/FactCheck';

import { useAppStore } from '@/store/useAppStore';
import { hasAnyRole } from '@/services/authz';
import type { SessionRole } from '@/types/session';

export const DRAWER_WIDTH = 260;

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactElement;
  roles?: SessionRole[];
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', path: '/dashboard', icon: <DashboardIcon /> },
  { label: 'Job Search', path: '/jobs', icon: <WorkIcon /> },
  { label: 'Candidates', path: '/candidates', icon: <PeopleIcon /> },
  { label: 'Applications', path: '/applications', icon: <SendIcon /> },
  { label: 'Resumes', path: '/resumes', icon: <DescriptionIcon /> },
  { label: 'Analytics', path: '/analytics', icon: <BarChartIcon /> },
  {
    label: 'Operations Queue',
    path: '/operations',
    icon: <FactCheckIcon />,
    roles: ['operator', 'admin', 'owner'],
  },
  { label: 'Settings', path: '/settings', icon: <SettingsIcon /> },
];

function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const sidebarOpen = useAppStore((s) => s.sidebarOpen);
  const setSidebarOpen = useAppStore((s) => s.setSidebarOpen);
  const tenantId = useAppStore((s) => s.authTenantId);
  const role = useAppStore((s) => s.authRole);

  const drawerContent = (
    <Box>
      <Toolbar sx={{ px: 2, justifyContent: 'space-between' }}>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <SmartToyIcon color="primary" sx={{ mr: 1.5 }} />
          <Typography variant="h6" noWrap color="primary">
            AutoApply AI
          </Typography>
        </Box>
      </Toolbar>
      <Box sx={{ px: 2, pb: 1 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
          Tenant
        </Typography>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {tenantId ?? 'Unscoped session'}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'capitalize' }}>
          Role: {role ?? 'none'}
        </Typography>
      </Box>
      <Divider />
      <List sx={{ px: 1, pt: 1 }}>
        {NAV_ITEMS.filter((item) => hasAnyRole(role, item.roles)).map((item) => {
          const selected = location.pathname === item.path;
          return (
            <ListItem key={item.path} disablePadding sx={{ mb: 0.5 }}>
              <ListItemButton
                selected={selected}
                onClick={() => {
                  navigate(item.path);
                  setSidebarOpen(false);
                }}
                sx={{
                  borderRadius: 1,
                  '&.Mui-selected': {
                    backgroundColor: 'primary.main',
                    color: 'white',
                    '&:hover': {
                      backgroundColor: 'primary.dark',
                    },
                    '& .MuiListItemIcon-root': {
                      color: 'white',
                    },
                  },
                }}
              >
                <ListItemIcon sx={{ minWidth: 40 }}>{item.icon}</ListItemIcon>
                <ListItemText primary={item.label} />
              </ListItemButton>
            </ListItem>
          );
        })}
      </List>
    </Box>
  );

  return (
    <Box component="nav" sx={{ width: { md: DRAWER_WIDTH }, flexShrink: 0 }}>
      <Drawer
        variant="temporary"
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{
          display: { xs: 'block', md: 'none' },
          '& .MuiDrawer-paper': { width: DRAWER_WIDTH },
        }}
      >
        {drawerContent}
      </Drawer>

      <Drawer
        variant="permanent"
        sx={{
          display: { xs: 'none', md: 'block' },
          '& .MuiDrawer-paper': { width: DRAWER_WIDTH, boxSizing: 'border-box' },
        }}
        open
      >
        {drawerContent}
      </Drawer>
    </Box>
  );
}

export default Sidebar;
