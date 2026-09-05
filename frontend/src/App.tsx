// App.tsx (esqueleto; a Task 4 preenche as rotas)
import { Routes, Route } from "react-router-dom";

export function App() {
  return (
    <div className="app">
      <nav className="nav"><div className="brand">Chess Trainer</div></nav>
      <main className="content">
        <Routes>
          <Route path="*" element={<h1>Chess Trainer</h1>} />
        </Routes>
      </main>
    </div>
  );
}
