import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { chapterPgnUrl, studyPgnUrl } from "../api/client";
import { useChapterActions, useStudy, useStudyEditor, useToggleChapterMode } from "../api/queries";
import type { ChapterOut, StudyDetail } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { Modal } from "../components/Modal";
import { NewChapterModal, StudyHeader } from "../studies/StudyEditor";

/** Importado do Lichess (respostas antigas não trazem `origin`). */
function importado(s: StudyDetail): boolean {
  return s.origin ? s.origin === "lichess" : s.lichess_id !== null;
}

/** A ordem dos capítulos com `at` trocado com o vizinho. */
function reordenar(chapters: ChapterOut[], at: number, delta: number): string[] {
  const ids = chapters.map((c) => c.id);
  const to = at + delta;
  [ids[at], ids[to]] = [ids[to], ids[at]];
  return ids;
}

export function StudyDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { data, error, isFetching, isLoading } = useStudy(id);
  const { update } = useStudyEditor();
  const { create, duplicate, remove } = useChapterActions(id);
  const toggleModo = useToggleChapterMode(id);
  const [novo, setNovo] = useState(false);
  const [apagar, setApagar] = useState<ChapterOut | null>(null);
  // capítulo que acabou de virar exercício mas não tem lance nenhum: o
  // servidor não gera exercício, avisamos aqui por alguns segundos
  const [semLances, setSemLances] = useState<string | null>(null);

  // `isFetching` entra junto: depois de reordenar, a lista na tela ainda é a
  // antiga até a busca voltar, e um segundo ↑/↓ mandaria a ordem errada.
  const mexendo = isFetching || update.isPending || duplicate.isPending || remove.isPending;

  return (
    <>
      {data ? (
        <StudyHeader
          study={data}
          saving={update.isPending}
          error={update.error}
          onSave={(body) => update.mutate({ id, body })}
        />
      ) : (
        <h1>Estudo</h1>
      )}
      <ErrorBox error={error} />
      <ErrorBox error={create.error ?? duplicate.error ?? remove.error ?? toggleModo.error} />
      {isLoading && <p className="muted">Carregando…</p>}
      {data && (
        <>
          <div className="muted" style={{ marginBottom: 12 }}>
            {data.author || "sem autor"}
            {data.source_url && (
              <> · <a href={data.source_url} target="_blank" rel="noreferrer">ver no Lichess</a></>
            )}
          </div>
          {importado(data) && (
            <div className="msg">Estudo importado: reimportar sobrescreve as edições feitas aqui.</div>
          )}
          <div className="row" style={{ marginBottom: 12 }}>
            {data.exercise_count > 0 && (
              <button onClick={() => navigate(`/treinar?mode=study&study=${id}`)}>Treinar este estudo</button>
            )}
            <button className="primary" onClick={() => setNovo(true)}>Novo capítulo</button>
            <a href={studyPgnUrl(id)} download>Exportar PGN</a>
            <Link to="/estudos" className="muted">← todos os estudos</Link>
          </div>
          <div className="card" style={{ padding: 0 }}>
            {data.chapters.map((c, i) => {
              const novoModo = c.mode === "read" ? "gamebook" : "read";
              const rotuloModo = c.mode === "read" ? "Treinar como exercício" : "Virar leitura";
              const trocandoModo = toggleModo.isPending && toggleModo.variables?.cid === c.id;
              return (
                <div key={c.id} style={{ padding: "10px 16px", borderBottom: "1px solid var(--line)" }}>
                  <div className="row" style={{ alignItems: "baseline" }}>
                    <span className="muted">{c.order}.</span>
                    <b>{c.name}</b>
                    <span className="tag">{c.mode === "gamebook" ? "exercício" : "leitura (sem exercício)"}</span>
                    {!c.in_queue && <span className="tag">fora da repetição</span>}
                    {semLances === c.id && <span className="muted">sem lances: não vira exercício</span>}
                  </div>
                  {c.intro_comment && <div className="muted">{c.intro_comment}</div>}
                  <div className="row" style={{ marginTop: 6 }}>
                    <Link to={`/estudos/${id}/capitulos/${c.id}`} aria-label={`ver "${c.name}"`}>Ver</Link>
                    <Link to={`/estudos/${id}/capitulos/${c.id}/editar`} aria-label={`editar "${c.name}"`}>Editar</Link>
                    {/* só gamebook tem exercício: virar leitura tira o dele da repetição */}
                    {c.mode === "gamebook" && c.puzzle_id && c.in_queue && (
                      <button onClick={() => navigate(`/treinar?puzzle=${c.puzzle_id}`)}>Treinar este</button>
                    )}
                    <button
                      disabled={trocandoModo}
                      onClick={() =>
                        toggleModo.mutate(
                          { cid: c.id, mode: novoModo },
                          {
                            onSuccess: (ch) => {
                              setSemLances(ch.mode === "gamebook" && ch.puzzle_id === null ? ch.id : null);
                            },
                          },
                        )
                      }
                    >
                      {rotuloModo}
                    </button>
                    <button
                      aria-label={`duplicar "${c.name}"`}
                      disabled={mexendo}
                      onClick={() => duplicate.mutate(c.id)}
                    >
                      Duplicar
                    </button>
                    <button
                      className="danger"
                      aria-label={`apagar "${c.name}"`}
                      onClick={() => setApagar(c)}
                    >
                      Apagar
                    </button>
                    <button
                      aria-label={`mover "${c.name}" para cima`}
                      disabled={mexendo || i === 0}
                      onClick={() => update.mutate({ id, body: { chapter_order: reordenar(data.chapters, i, -1) } })}
                    >
                      ↑
                    </button>
                    <button
                      aria-label={`mover "${c.name}" para baixo`}
                      disabled={mexendo || i === data.chapters.length - 1}
                      onClick={() => update.mutate({ id, body: { chapter_order: reordenar(data.chapters, i, 1) } })}
                    >
                      ↓
                    </button>
                    <a href={chapterPgnUrl(id, c.id)} download aria-label={`PGN de "${c.name}"`}>PGN</a>
                    {c.lichess_url && (
                      <a href={c.lichess_url} target="_blank" rel="noreferrer">ver no Lichess</a>
                    )}
                  </div>
                </div>
              );
            })}
            {data.chapters.length === 0 && (
              <p className="muted" style={{ padding: 16 }}>
                Estudo sem capítulos: use "Novo capítulo" para começar.
              </p>
            )}
          </div>
        </>
      )}

      {novo && data && (
        <NewChapterModal
          count={data.chapters.length}
          saving={create.isPending}
          error={create.error}
          onClose={() => setNovo(false)}
          onCreate={(body) =>
            create.mutate(body, {
              onSuccess: (cap) => {
                setNovo(false);
                navigate(`/estudos/${id}/capitulos/${cap.id}/editar`);
              },
            })
          }
        />
      )}

      <Modal open={apagar !== null} title={`Apagar "${apagar?.name ?? ""}"?`} onClose={() => setApagar(null)}>
        <p>Apaga o capítulo, o exercício e o histórico dele. Não pode ser desfeito.</p>
        <div className="row">
          <button
            className="danger"
            disabled={remove.isPending}
            onClick={() => { if (apagar) remove.mutate(apagar.id, { onSettled: () => setApagar(null) }); }}
          >
            Apagar mesmo assim
          </button>
          <button onClick={() => setApagar(null)}>Cancelar</button>
        </div>
      </Modal>
    </>
  );
}
