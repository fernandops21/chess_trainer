import { Routes, Route } from "react-router-dom";
import { useJobWatcher } from "./api/queries";
import { Nav } from "./components/Nav";
import { AnalysisPage } from "./pages/AnalysisPage";
import { DashboardPage } from "./pages/DashboardPage";
import { GamesPage } from "./pages/GamesPage";
import { GameDetailPage } from "./pages/GameDetailPage";
import { MistakesPage } from "./pages/MistakesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StudiesPage } from "./pages/StudiesPage";
import { StudyDetailPage } from "./pages/StudyDetailPage";
import { TrainPage } from "./train/TrainPage";

export function App() {
  useJobWatcher();
  return (
    <div className="app">
      <Nav />
      <main className="content">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/treinar" element={<TrainPage />} />
          <Route path="/analise" element={<AnalysisPage />} />
          <Route path="/estudos" element={<StudiesPage />} />
          <Route path="/estudos/:id" element={<StudyDetailPage />} />
          <Route path="/partidas" element={<GamesPage />} />
          <Route path="/partidas/:id" element={<GameDetailPage />} />
          <Route path="/erros" element={<MistakesPage />} />
          <Route path="/config" element={<SettingsPage />} />
          <Route path="*" element={<DashboardPage />} />
        </Routes>
      </main>
    </div>
  );
}
