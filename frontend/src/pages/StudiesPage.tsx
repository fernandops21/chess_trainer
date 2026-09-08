import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useImportStudy, useStatus, useStudies, useStudyActions, useStudyEditor } from "../api/queries";
import type { StudyOut } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { JobCard } from "../components/JobCard";
import { Modal } from "../components/Modal";
import { NewStudyModal } from "../studies/StudyEditor";
import { formatDate } from "../lib/format";

const plural = (n: number, um: string, muitos: string) => `${n} ${n === 1 ? um : muitos}`;

/** "3 capítulos · 2 na repetição · 1 vencido hoje" */
function counts(s: StudyOut): string {
  return [
    plural(s.chapter_count, "capítulo", "capítulos"),
    `${s.in_queue} na repetição`,
    `${s.due_today} ${s.due_today === 1 ? "vencido" : "vencidos"} hoje`,
  ].join(" · ");
}

/** "livro.pgn" → "livro": o nome do arquivo vira o título do estudo. */
const semExtensao = (nome: string) => nome.replace(/\.[^.]+$/, "") || nome;

export function StudiesPage() {
  const navigate = useNavigate();
  const { data, error, isLoading } = useStudies();
  const importStudy = useImportStudy();
  const { reimport, setQueue, remove } = useStudyActions();
  const { create } = useStudyEditor();
  const [novo, setNovo] = useState(false);
  const [url, setUrl] = useState("");
  const [pgn, setPgn] = useState("");
  // leitura do arquivo escolhido que falhou: aparece na mesma caixa dos erros da API
  const [erroArquivo, setErroArquivo] = useState<Error | null>(null);
  const [showPgn, setShowPgn] = useState(false);
  const [confirm, setConfirm] = useState<StudyOut | null>(null);
  const { data: status } = useStatus();
  // uma tarefa já em andamento (importação de outro estudo, análise…) recusaria a
  // próxima com 409: o botão fica desligado enquanto ela roda
  const busy = importStudy.isPending || reimport.isPending || status?.job.state === "running";

  return (
    <>
      <div className="row" style={{ alignItems: "baseline" }}>
        <h1 style={{ marginBottom: 0 }}>Estudos</h1>
        <button className="primary" onClick={() => setNovo(true)}>Novo estudo</button>
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Importar</h3>
        <div className="row">
          <input
            style={{ flex: "1 1 320px" }}
            placeholder="https://lichess.org/study/xxxxxxxx"
            aria-label="URL do estudo no Lichess"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button
            className="primary"
            disabled={busy || url.trim() === ""}
            onClick={() => { importStudy.mutate({ url: url.trim() }); setUrl(""); }}
          >
            Importar
          </button>
          <button onClick={() => setShowPgn(!showPgn)}>{showPgn ? "usar a URL" : "colar PGN"}</button>
        </div>
        <div className="muted">
          Só estudos públicos. Se o estudo for privado, exporte o PGN no Lichess e cole aqui.
        </div>
        {showPgn && (
          <div style={{ marginTop: 10 }}>
            <textarea
              style={{ width: "100%", minHeight: 120 }}
              aria-label="PGN do estudo"
              placeholder="Cole aqui o PGN exportado do estudo"
              value={pgn}
              onChange={(e) => setPgn(e.target.value)}
            />
            <div className="row">
              <button
                className="primary"
                disabled={busy || pgn.trim() === ""}
                onClick={() => { importStudy.mutate({ pgn }); setPgn(""); }}
              >
                Importar PGN
              </button>
            </div>
          </div>
        )}
        <div style={{ marginTop: 10 }}>
          <input
            type="file"
            accept=".pgn,text/plain"
            aria-label="Arquivo PGN"
            disabled={busy}
            onChange={(e) => {
              setErroArquivo(null);
              const arquivo = e.target.files?.[0];
              // limpa a escolha para que o mesmo arquivo possa ser importado de novo
              e.target.value = "";
              if (!arquivo) return;
              arquivo.text().then(
                (texto) => importStudy.mutate({ pgn: texto, title: semExtensao(arquivo.name) }),
                () => setErroArquivo(new Error(`Não deu para ler o arquivo ${arquivo.name}.`)),
              );
            }}
          />
          <div className="muted">
            Coleções de partidas em PGN (livros comprados em PGN, bases exportadas) viram um estudo
            com um capítulo por partida.
          </div>
        </div>
        <ErrorBox error={importStudy.error ?? reimport.error ?? setQueue.error ?? remove.error ?? erroArquivo} />
      </div>
      <JobCard />
      <ErrorBox error={error} />
      {isLoading && <p className="muted">Carregando…</p>}
      {data?.length === 0 && (
        <div className="card">
          <p>Nenhum estudo importado ainda.</p>
          <p className="muted">
            Cole acima o endereço do estudo no Lichess (lichess.org/study/…) e cada capítulo com modo
            "gamebook" vira um exercício da repetição espaçada.
          </p>
        </div>
      )}
      {data?.map((s) => (
        <div className="card" key={s.id}>
          <h3 style={{ marginTop: 0 }}><Link to={`/estudos/${s.id}`}>{s.title}</Link></h3>
          <div className="muted">
            {s.author || "sem autor"}
            {s.imported_at && ` · importado em ${formatDate(s.imported_at)}`}
          </div>
          <div>{counts(s)}</div>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="primary" onClick={() => navigate(`/treinar?mode=study&study=${s.id}`)}>Treinar este estudo</button>
            {s.lichess_id && (
              <button disabled={busy} onClick={() => reimport.mutate(s.id)}>Reimportar</button>
            )}
            {s.exercise_count > 0 ? (
              <button
                disabled={setQueue.isPending}
                onClick={() => setQueue.mutate({ id: s.id, in_queue: s.in_queue === 0 })}
              >
                {s.in_queue > 0 ? "Tirar da repetição" : "Voltar para a repetição"}
              </button>
            ) : (
              // sem nenhum capítulo em modo gamebook não há o que pôr ou tirar da fila
              <span className="muted">sem exercícios: só capítulos de leitura</span>
            )}
            <button className="danger" onClick={() => setConfirm(s)}>Remover</button>
          </div>
        </div>
      ))}
      {novo && (
        <NewStudyModal
          saving={create.isPending}
          error={create.error}
          onClose={() => setNovo(false)}
          onCreate={(body) =>
            create.mutate(body, {
              onSuccess: (s) => { setNovo(false); navigate(`/estudos/${s.id}`); },
            })
          }
        />
      )}
      <Modal open={confirm !== null} title={`Remover "${confirm?.title ?? ""}"?`} onClose={() => setConfirm(null)}>
        <p>Apaga o estudo, os capítulos, os exercícios e o histórico deles. Não pode ser desfeito.</p>
        <div className="row">
          <button
            className="danger"
            onClick={() => { if (confirm) remove.mutate(confirm.id); setConfirm(null); }}
          >
            Remover mesmo assim
          </button>
          <button onClick={() => setConfirm(null)}>Cancelar</button>
        </div>
      </Modal>
    </>
  );
}
