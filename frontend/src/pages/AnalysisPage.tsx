import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Chess } from "chess.js";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
import { AnalysisBoard } from "../analysis/AnalysisBoard";

export function AnalysisPage() {
  const [params] = useSearchParams();
  // sem FEN na URL, abre na posição inicial (link direto ou item de menu)
  const fen = params.get("fen") || START_FEN;
  const orientation = params.get("orientation") === "black" ? "black" : "white";
  const back = params.get("back") || "/";

  const valid = useMemo(() => {
    try {
      new Chess(fen);
      return true;
    } catch {
      return false;
    }
  }, [fen]);

  if (!valid) {
    return (
      <>
        <h1>Análise</h1>
        <div className="card">
          <p>FEN inválido.</p>
          <Link to="/">Voltar ao Painel</Link>
        </div>
      </>
    );
  }

  return (
    <>
      <h1>Análise</h1>
      <AnalysisBoard key={fen} fenStart={fen} orientation={orientation} backTo={back} />
    </>
  );
}
