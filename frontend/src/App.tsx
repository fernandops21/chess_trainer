import { Routes, Route } from "react-router-dom";
import { useJobWatcher } from "./api/queries";
import { Nav } from "./components/Nav";
import { BlocoGlobal } from "./train/BlocoContext";
import { AnalysisPage } from "./pages/AnalysisPage";
import { DashboardPage } from "./pages/DashboardPage";
import { GamesPage } from "./pages/GamesPage";
import { GameDetailPage } from "./pages/GameDetailPage";
import { MistakesPage } from "./pages/MistakesPage";
import { ProgressPage } from "./pages/ProgressPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StudiesPage } from "./pages/StudiesPage";
import { StudyDetailPage } from "./pages/StudyDetailPage";
import { ChapterEditorPage } from "./pages/ChapterEditorPage";
import { ChapterViewPage } from "./pages/ChapterViewPage";
import { ReviewPage } from "./train/ReviewPage";
import { TrainPage } from "./train/TrainPage";

export function App() {
  useJobWatcher();
  return (
    <div className="app">
      <Nav />
      <main className="content">
        <BlocoGlobal>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/revisar" element={<ReviewPage />} />
          <Route path="/treinar" element={<TrainPage />} />
          <Route path="/analise" element={<AnalysisPage />} />
          <Route path="/estudos" element={<StudiesPage />} />
          <Route path="/estudos/:id" element={<StudyDetailPage />} />
          <Route path="/estudos/:id/capitulos/:cid" element={<ChapterViewPage />} />
          <Route path="/estudos/:id/capitulos/:cid/editar" element={<ChapterEditorPage />} />
          <Route path="/partidas" element={<GamesPage />} />
          <Route path="/partidas/:id" element={<GameDetailPage />} />
          <Route path="/erros" element={<MistakesPage />} />
          <Route path="/progresso" element={<ProgressPage />} />
          <Route path="/config" element={<SettingsPage />} />
          <Route path="*" element={<DashboardPage />} />
        </Routes>
        </BlocoGlobal>
      </main>
    </div>
  );
}
