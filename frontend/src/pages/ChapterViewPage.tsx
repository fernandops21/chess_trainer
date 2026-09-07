import { useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AnalysisBoard } from "../analysis/AnalysisBoard";
import { emptyTree } from "../analysis/moveTree";
import { useChapter } from "../api/queries";
import { ErrorBox } from "../components/ErrorBox";
import { chapterPgnUrl } from "../api/client";

/**
 * Leitura de um capítulo: a mesma árvore do editor, só que sem edição — os
 * comentários e as marcações do autor aparecem enquanto se navega pelos
 * lances (é assim que se lê uma partida anotada importada do Lichess).
 *
 * O enunciado não sai aqui: quem o mostra é o cartão de leitura do próprio
 * tabuleiro, junto com o comentário do lance atual.
 */
export function ChapterViewPage() {
  const { id = "", cid = "" } = useParams();
  const navigate = useNavigate();
  const { data, error, isLoading } = useChapter(id, cid);

  // memoizada: uma árvore nova a cada render reiniciaria a navegação do tabuleiro
  const tree = useMemo(
    () => (data ? data.tree ?? emptyTree(data.fen, data.orientation) : null),
    [data],
  );

  return (
    <>
      <div className="row" style={{ alignItems: "baseline" }}>
        <h1 style={{ marginBottom: 0 }}>{data?.name ?? "Capítulo"}</h1>
        <Link to={`/estudos/${id}`}>Voltar ao estudo</Link>
      </div>
      <ErrorBox error={error} />
      {isLoading && <p className="muted">Carregando…</p>}
      {data && tree && (
        <>
          <div className="row" style={{ marginBottom: 10 }}>
            {/* só gamebook tem exercício: virar leitura tira o dele da repetição */}
            {data.mode === "gamebook" && data.puzzle_id && data.in_queue && (
              <button className="primary" onClick={() => navigate(`/treinar?puzzle=${data.puzzle_id}`)}>
                Treinar este
              </button>
            )}
            <Link to={`/estudos/${id}/capitulos/${cid}/editar`}>Editar</Link>
            <a href={chapterPgnUrl(id, cid)} download>Exportar PGN</a>
            {data.lichess_url && (
              <a href={data.lichess_url} target="_blank" rel="noreferrer">ver no Lichess</a>
            )}
          </div>
          <AnalysisBoard tree={tree} />
        </>
      )}
    </>
  );
}
