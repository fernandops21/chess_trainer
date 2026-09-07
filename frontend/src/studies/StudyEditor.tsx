import { useMemo, useState } from "react";
import { Chess } from "chess.js";
import { useSettings } from "../api/queries";
import type { ChapterIn, ChapterOut, Color, StudyDetail } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { Modal } from "../components/Modal";

export const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

/** Quem joga na FEN: é a orientação natural do capítulo. */
function orientationOf(fen: string): Color {
  return fen.split(" ")[1] === "b" ? "black" : "white";
}

export interface StudyHeaderProps {
  study: StudyDetail;
  saving: boolean;
  error: unknown;
  onSave: (body: { title: string; author: string }) => void;
}

/**
 * Título e autor do estudo, editáveis no lugar: "Editar título" troca o
 * cabeçalho por dois campos e "Salvar" manda o `PUT`.
 */
export function StudyHeader({ study, saving, error, onSave }: StudyHeaderProps) {
  const [editando, setEditando] = useState(false);
  const [titulo, setTitulo] = useState(study.title);
  const [autor, setAutor] = useState(study.author);

  if (!editando) {
    return (
      <>
        <div className="row" style={{ alignItems: "baseline" }}>
          <h1 style={{ marginBottom: 0 }}>{study.title}</h1>
          <button
            onClick={() => { setTitulo(study.title); setAutor(study.author); setEditando(true); }}
          >
            Editar título
          </button>
        </div>
        <ErrorBox error={error} />
      </>
    );
  }

  return (
    <div className="card">
      <div className="row">
        <label style={{ flex: "1 1 260px" }}>
          <div className="muted">Título</div>
          <input
            aria-label="Título"
            style={{ width: "100%" }}
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
          />
        </label>
        <label style={{ flex: "1 1 200px" }}>
          <div className="muted">Autor</div>
          <input
            aria-label="Autor"
            style={{ width: "100%" }}
            value={autor}
            onChange={(e) => setAutor(e.target.value)}
          />
        </label>
      </div>
      <ErrorBox error={error} />
      <div className="row" style={{ marginTop: 8 }}>
        <button
          className="primary"
          disabled={saving || titulo.trim() === ""}
          onClick={() => { onSave({ title: titulo.trim(), author: autor.trim() }); setEditando(false); }}
        >
          Salvar
        </button>
        <button onClick={() => setEditando(false)}>Cancelar</button>
      </div>
    </div>
  );
}

export interface NewChapterModalProps {
  /** Quantos capítulos o estudo já tem: dá o nome sugerido. */
  count: number;
  saving: boolean;
  error: unknown;
  onCreate: (body: ChapterIn) => void;
  onClose: () => void;
}

/** "Novo capítulo": nome, posição inicial (padrão ou FEN colada) e modo. */
export function NewChapterModal({ count, saving, error, onCreate, onClose }: NewChapterModalProps) {
  const [nome, setNome] = useState(`Capítulo ${count + 1}`);
  const [origem, setOrigem] = useState<"padrao" | "fen">("padrao");
  const [fen, setFen] = useState("");
  const [modo, setModo] = useState<ChapterOut["mode"]>("gamebook");

  const fenLimpa = fen.trim();
  const fenValida = useMemo(() => {
    if (origem === "padrao") return true;
    if (fenLimpa === "") return false;
    try {
      new Chess(fenLimpa);
      return true;
    } catch {
      return false;
    }
  }, [origem, fenLimpa]);

  const impedido = saving || nome.trim() === "" || !fenValida;

  const criar = () => {
    const body: ChapterIn = { name: nome.trim(), mode: modo, orientation: "white" };
    if (origem === "fen") {
      body.fen = fenLimpa;
      body.orientation = orientationOf(fenLimpa);
    }
    onCreate(body);
  };

  return (
    <Modal open title="Novo capítulo" onClose={onClose}>
      <div style={{ marginBottom: 10 }}>
        <div className="muted">Nome do capítulo</div>
        <input
          aria-label="Nome do capítulo"
          style={{ width: "100%" }}
          value={nome}
          onChange={(e) => setNome(e.target.value)}
        />
      </div>

      <div style={{ marginBottom: 10 }}>
        <div className="muted">Posição inicial</div>
        <div className="row">
          <input
            type="radio"
            id="pos-padrao"
            name="posicao"
            checked={origem === "padrao"}
            onChange={() => setOrigem("padrao")}
          />
          <label htmlFor="pos-padrao">posição padrão</label>
          <input
            type="radio"
            id="pos-fen"
            name="posicao"
            checked={origem === "fen"}
            onChange={() => setOrigem("fen")}
          />
          <label htmlFor="pos-fen">FEN colada</label>
        </div>
        {origem === "fen" && (
          <>
            <input
              aria-label="FEN"
              style={{ width: "100%" }}
              placeholder="8/8/8/8/8/5k2/8/7K b - - 0 1"
              value={fen}
              onChange={(e) => setFen(e.target.value)}
            />
            {!fenValida && fenLimpa !== "" && <div className="msg bad">FEN inválido.</div>}
          </>
        )}
        <div className="muted" style={{ marginTop: 6 }}>
          Para partir de uma posição montada no tabuleiro, use "Salvar como capítulo" na Análise.
        </div>
      </div>

      <div style={{ marginBottom: 10 }}>
        <div className="muted">Modo</div>
        <select aria-label="Modo" value={modo} onChange={(e) => setModo(e.target.value as ChapterOut["mode"])}>
          <option value="gamebook">exercício</option>
          <option value="read">leitura</option>
        </select>
      </div>

      <ErrorBox error={error} />
      <div className="row">
        <button className="primary" disabled={impedido} onClick={criar}>Criar capítulo</button>
        <button onClick={onClose}>Cancelar</button>
      </div>
    </Modal>
  );
}

export interface NewStudyModalProps {
  saving: boolean;
  error: unknown;
  onCreate: (body: { title: string; author: string }) => void;
  onClose: () => void;
}

/**
 * "Novo estudo": título e autor, só isso — os capítulos vêm depois. O autor já
 * vem com o nome configurado (é quase sempre quem escreve o estudo aqui) e
 * continua editável: `null` quer dizer "ainda não mexeram no campo".
 */
export function NewStudyModal({ saving, error, onCreate, onClose }: NewStudyModalProps) {
  const { data: settings } = useSettings();
  const [titulo, setTitulo] = useState("");
  const [autor, setAutor] = useState<string | null>(null);
  const nomeAutor = autor ?? settings?.chesscom_username ?? "";
  return (
    <Modal open title="Novo estudo" onClose={onClose}>
      <div style={{ marginBottom: 10 }}>
        <div className="muted">Título do estudo</div>
        <input
          aria-label="Título do estudo"
          style={{ width: "100%" }}
          value={titulo}
          onChange={(e) => setTitulo(e.target.value)}
        />
        <div className="muted" style={{ marginTop: 6 }}>Autor (opcional)</div>
        <input
          aria-label="Autor"
          style={{ width: "100%" }}
          value={nomeAutor}
          onChange={(e) => setAutor(e.target.value)}
        />
      </div>
      <ErrorBox error={error} />
      <div className="row">
        <button
          className="primary"
          disabled={saving || titulo.trim() === ""}
          onClick={() => onCreate({ title: titulo.trim(), author: nomeAutor.trim() })}
        >
          Criar estudo
        </button>
        <button onClick={onClose}>Cancelar</button>
      </div>
    </Modal>
  );
}
