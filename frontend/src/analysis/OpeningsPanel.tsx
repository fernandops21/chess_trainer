import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { useOpenings } from "../api/queries";
import type { OpeningsDb } from "../api/types";
import { errorMessage } from "../components/ErrorBox";
import { storage } from "../lib/storage";

const nf = new Intl.NumberFormat("pt-BR");

export interface OpeningsPanelProps {
  fen: string;
  /** Joga o lance escolhido na árvore (como as linhas do motor). */
  onPlay: (uci: string) => void;
}

/** Faixa de resultados: brancas, empates e pretas em três segmentos. */
function ResultBar({ white, draws, black }: { white: number; draws: number; black: number }) {
  const total = white + draws + black;
  const pct = (n: number) => (total > 0 ? Math.round((n / total) * 100) : 0);
  const [pw, pd, pb] = [pct(white), pct(draws), pct(black)];
  return (
    <div className="wdl" role="img" aria-label={`brancas ${pw}%, empates ${pd}%, pretas ${pb}%`}>
      <span className="wdl-w" style={{ width: `${pw}%` }} title={`brancas ${pw}%`} />
      <span className="wdl-d" style={{ width: `${pd}%` }} title={`empates ${pd}%`} />
      <span className="wdl-b" style={{ width: `${pb}%` }} title={`pretas ${pb}%`} />
    </div>
  );
}

/**
 * Falta de token e token recusado voltam como 400 do proxy: nesses dois casos a
 * saída é a mesma tela (Configurações), então o aviso leva o link. Os outros
 * erros (limite do Lichess, explorador fora do ar) só mostram a mensagem.
 */
function ErroAberturas({ error }: { error: unknown }) {
  const msg = errorMessage(error);
  const doToken = error instanceof ApiError && error.status === 400 && msg.toLowerCase().includes("token");
  return (
    <div className="msg bad" role="alert">
      {msg}
      {doToken && (
        <>
          {" — "}
          <Link to="/config">Configurações</Link>
        </>
      )}
    </div>
  );
}

/**
 * Livro de aberturas da posição atual: o que mestres (ou jogadores do Lichess)
 * jogaram daqui, com quantas partidas e como terminaram. Clicar num lance joga
 * ele no tabuleiro. A base escolhida fica guardada entre as visitas.
 */
export function OpeningsPanel({ fen, onPlay }: OpeningsPanelProps) {
  const [db, setDb] = useState<OpeningsDb>(() =>
    storage.get<OpeningsDb>("analysis.openingsDb", "masters") === "lichess" ? "lichess" : "masters",
  );
  const { data, error, isPending } = useOpenings(fen, db);

  const trocarBase = (valor: string) => {
    const base: OpeningsDb = valor === "lichess" ? "lichess" : "masters";
    setDb(base);
    storage.set("analysis.openingsDb", base);
  };

  const comRating = (data?.moves ?? []).some((m) => m.avg_rating !== null);

  return (
    <div className="card">
      <label className="row" style={{ justifyContent: "space-between" }}>
        Base de partidas
        <select value={db} onChange={(e) => trocarBase(e.target.value)}>
          <option value="masters">Mestres</option>
          <option value="lichess">Jogadores (Lichess)</option>
        </select>
      </label>
      {data?.opening && (
        <div style={{ marginTop: 8, fontWeight: 600 }}>
          {data.opening.eco} · {data.opening.name}
        </div>
      )}
      {isPending && <div className="muted">consultando…</div>}
      {error && <ErroAberturas error={error} />}
      {data &&
        (data.moves.length === 0 ? (
          <div className="muted" style={{ marginTop: 8 }}>Sem partidas nesta posição.</div>
        ) : (
          <>
            <table className="openings">
              <thead>
                <tr>
                  <th>lance</th>
                  <th>partidas</th>
                  <th>brancas / empates / pretas</th>
                  {comRating && <th>rating</th>}
                </tr>
              </thead>
              <tbody>
                {data.moves.map((m) => (
                  <tr key={m.uci}>
                    <td>
                      <button className="opening-san" onClick={() => onPlay(m.uci)}>{m.san}</button>
                    </td>
                    <td className="num">{nf.format(m.games)}</td>
                    <td>
                      <ResultBar white={m.white} draws={m.draws} black={m.black} />
                    </td>
                    {comRating && (
                      <td className="num muted">{m.avg_rating === null ? "—" : nf.format(m.avg_rating)}</td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="muted" style={{ marginTop: 8 }}>
              {nf.format(data.total)} partidas nesta posição
            </div>
          </>
        ))}
    </div>
  );
}
