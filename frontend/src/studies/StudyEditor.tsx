import { useMemo, useState } from "react";
import { Chess } from "chess.js";
import { PositionEditor } from "../analysis/PositionEditor";
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

/** "Novo capítulo": nome, posição inicial (padrão, FEN colada ou montada) e modo. */
export function NewChapterModal({ count, saving, error, onCreate, onClose }: NewChapterModalProps) {
  // vazio de propósito: com o padrão dentro do campo, quem digita acaba com
  // "Capítulo 2Francesa" — o padrão fica no `placeholder` e vale se ficar vazio
  const nomePadrao = `Capítulo ${count + 1}`;
  const [nome, setNome] = useState("");
  const [origem, setOrigem] = useState<"padrao" | "fen" | "montada">("padrao");
  const [fen, setFen] = useState("");
  const [fenMontada, setFenMontada] = useState("");
  const [montando, setMontando] = useState(false);
  const [modo, setModo] = useState<ChapterOut["mode"]>("gamebook");

  const fenLimpa = fen.trim();
  const fenValida = useMemo(() => {
    if (origem === "padrao") return true;
    if (origem === "montada") return fenMontada !== "";
    if (fenLimpa === "") return false;
    try {
      new Chess(fenLimpa);
      return true;
    } catch {
      return false;
    }
  }, [origem, fenLimpa, fenMontada]);

  const impedido = saving || !fenValida;

  const criar = () => {
    const body: ChapterIn = { name: nome.trim() || nomePadrao, mode: modo, orientation: "white" };
    const escolhida = origem === "fen" ? fenLimpa : origem === "montada" ? fenMontada : "";
    if (escolhida !== "") {
      body.fen = escolhida;
      body.orientation = orientationOf(escolhida);
    }
    onCreate(body);
  };

  // O tabuleiro não cabe junto com o resto do formulário: enquanto monta, o
  // modal é só o editor. O que já foi preenchido continua aqui, no estado.
  if (montando) {
    return (
      <Modal open wide title="Montar posição" onClose={() => setMontando(false)}>
        <PositionEditor
          initialFen={fenMontada || undefined}
          onUse={(f) => {
            setFenMontada(f);
            setMontando(false);
          }}
          onCancel={() => setMontando(false)}
        />
      </Modal>
    );
  }

  return (
    <Modal open title="Novo capítulo" onClose={onClose}>
      <div style={{ marginBottom: 10 }}>
        <div className="muted">Nome do capítulo</div>
        <input
          aria-label="Nome do capítulo"
          style={{ width: "100%" }}
          placeholder={nomePadrao}
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
          <input
            type="radio"
            id="pos-montada"
            name="posicao"
            checked={origem === "montada"}
            onChange={() => setOrigem("montada")}
          />
          <label htmlFor="pos-montada">montar posição</label>
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
        {origem === "montada" && (
          <div className="row" style={{ marginTop: 6 }}>
            <button onClick={() => setMontando(true)}>
              {fenMontada === "" ? "Montar posição" : "Editar a posição"}
            </button>
            <span className="muted" style={{ wordBreak: "break-all" }}>
              {fenMontada === "" ? "nenhuma posição montada ainda" : fenMontada}
            </span>
          </div>
        )}
        <div className="muted" style={{ marginTop: 6 }}>
          Uma análise inteira também vira capítulo: use "Salvar como capítulo" na Análise.
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
