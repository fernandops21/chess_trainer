import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Chess } from "chess.js";
import { AnalysisBoard } from "../analysis/AnalysisBoard";
import { SaveChapterModal } from "../analysis/SaveChapterModal";
import { emptyTree } from "../analysis/moveTree";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export function AnalysisPage() {
  const [params] = useSearchParams();
  // sem FEN na URL, abre na posição inicial (link direto ou item de menu)
  const fen = params.get("fen") || START_FEN;
  const orientation = params.get("orientation") === "black" ? "black" : "white";
  const back = params.get("back") || "/";
  const [novoEstudo, setNovoEstudo] = useState(false);

  const valid = useMemo(() => {
    try {
      new Chess(fen);
      return true;
    } catch {
      return false;
    }
  }, [fen]);

  // trocar de FEN (ou de orientação) recomeça a análise numa árvore vazia
  const inicial = useMemo(() => emptyTree(valid ? fen : START_FEN, orientation), [fen, orientation, valid]);
  const [tree, setTree] = useState(inicial);
  useEffect(() => setTree(inicial), [inicial]);

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
      <div className="row" style={{ marginBottom: 12 }}>
        <button onClick={() => setNovoEstudo(true)}>Novo estudo</button>
        <span className="muted">Jogue os lances, monte as variações e salve como capítulo.</span>
      </div>
      <AnalysisBoard editable tree={tree} onTreeChange={setTree} backTo={back} showSaveAsChapter />
      {novoEstudo && <SaveChapterModal tree={tree} newStudy onClose={() => setNovoEstudo(false)} />}
    </>
  );
}
