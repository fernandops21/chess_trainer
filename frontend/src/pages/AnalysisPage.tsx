import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Chess } from "chess.js";
import { AnalysisBoard } from "../analysis/AnalysisBoard";

export function AnalysisPage() {
  const [params] = useSearchParams();
  const fen = params.get("fen");
  const orientation = params.get("orientation") === "black" ? "black" : "white";
  const back = params.get("back") || "/";

  const valid = useMemo(() => {
    if (!fen) return false;
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
          <p>FEN ausente ou inválido.</p>
          <Link to="/">Voltar ao Painel</Link>
        </div>
      </>
    );
  }

  return (
    <>
      <h1>Análise</h1>
      <AnalysisBoard key={fen} fenStart={fen!} orientation={orientation} backTo={back} />
    </>
  );
}
