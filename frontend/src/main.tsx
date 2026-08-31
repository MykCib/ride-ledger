import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import './styles.css';
import { DashboardPage } from './components/Dashboard';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DashboardPage page="overview" />} />
        <Route path="/rides" element={<DashboardPage page="rides" />} />
        <Route path="/rides/:rideId" element={<DashboardPage page="rides" />} />
        <Route path="/routes" element={<DashboardPage page="routes" />} />
        <Route path="/insights" element={<DashboardPage page="insights" />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
