import { useMemo, useState } from "react";
import type { Color, Key, Piece, Role } from "chessground/types";
import { Board } from "../board/Board";
import {
  START_FEN,
  boardFromFen,
  castlingAvailable,
  castlingFromFen,
  fenFromBoard,
  keepAvailable,
  parseFen,
  turnFromFen,
  validatePosition,
} from "./position";
import type { Castling, EditorBoard } from "./position";

/** O que a paleta tem escolhido: uma peça, a borracha, ou nada. */
type Escolha = Piece | "apagar" | null;

const ROLES: Role[] = ["king", "queen", "rook", "bishop", "knight", "pawn"];
const CORES: Color[] = ["white", "black"];

/** Nome da peça em português, com a concordância certa de cor. */
const NOME: Record<Role, Record<Color, string>> = {
  king: { white: "Rei branco", black: "Rei preto" },
  queen: { white: "Dama branca", black: "Dama preta" },
  rook: { white: "Torre branca", black: "Torre preta" },
  bishop: { white: "Bispo branco", black: "Bispo preto" },
  knight: { white: "Cavalo branco", black: "Cavalo preto" },
  pawn: { white: "Peão branco", black: "Peão preto" },
};

const GLIFO: Record<Color, Record<Role, string>> = {
  white: { king: "♔", queen: "♕", rook: "♖", bishop: "♗", knight: "♘", pawn: "♙" },
  black: { king: "♚", queen: "♛", rook: "♜", bishop: "♝", knight: "♞", pawn: "♟" },
};

const ROQUES: { chave: keyof Castling; rotulo: string; curto: string }[] = [
  { chave: "K", rotulo: "Roque pequeno das brancas", curto: "brancas O-O" },
  { chave: "Q", rotulo: "Roque grande das brancas", curto: "brancas O-O-O" },
  { chave: "k", rotulo: "Roque pequeno das pretas", curto: "pretas O-O" },
  { chave: "q", rotulo: "Roque grande das pretas", curto: "pretas O-O-O" },
];

const SEM_ROQUE: Castling = { K: false, Q: false, k: false, q: false };
const TODO_ROQUE: Castling = { K: true, Q: true, k: true, q: true };

export interface PositionEditorProps {
  /** Posição de onde partir (a inicial da partida, quando não vem nada). */
  initialFen?: string;
  orientation?: Color;
  /** Rótulo do botão que confirma; o padrão é "Usar posição". */
  useLabel?: string;
  onUse: (fen: string) => void;
  onCancel: () => void;
}

/**
 * Montagem de posição: paleta de peças, tabuleiro solto e os campos que a FEN
 * pede (lado a jogar e roques). O tabuleiro aqui não joga xadrez — clicar
 * coloca a peça escolhida, arrastar leva a peça para qualquer casa e soltar
 * fora do tabuleiro apaga. Enquanto a posição não fecha, "Usar posição" fica
 * desabilitado e os motivos aparecem na lista.
 */
export function PositionEditor({
  initialFen,
  orientation = "white",
  useLabel = "Usar posição",
  onUse,
  onCancel,
}: PositionEditorProps) {
  const base = initialFen ?? START_FEN;
  const [board, setBoard] = useState<EditorBoard>(() => boardFromFen(base));
  const [turn, setTurn] = useState<Color>(() => turnFromFen(base));
  const [castling, setCastling] = useState<Castling>(() => castlingFromFen(base));
  const [orient, setOrient] = useState<Color>(orientation);
  const [escolha, setEscolha] = useState<Escolha>(null);
  // texto digitado no campo FEN; `null` = mostrar a FEN da posição montada
  const [fenTexto, setFenTexto] = useState<string | null>(null);
  const [fenErro, setFenErro] = useState(false);

  const pode = useMemo(() => castlingAvailable(board), [board]);
  // roque que a posição não permite não entra na FEN, mas fica lembrado: repor
  // a torre no canto traz a marcação de volta
  const roques = keepAvailable(castling, board);
  const fen = fenFromBoard(board, turn, roques);
  const erros = useMemo(() => validatePosition(fen), [fen]);

  /** Toda mudança feita no tabuleiro ou nos controles devolve o campo FEN à posição. */
  const aplicar = (b: EditorBoard, t: Color = turn, c: Castling = castling) => {
    setBoard(b);
    setTurn(t);
    setCastling(c);
    setFenTexto(null);
    setFenErro(false);
  };

  const clicarCasa = (key: Key) => {
    if (!escolha) return;
    const b = new Map(board);
    if (escolha === "apagar") b.delete(key);
    else b.set(key, escolha);
    aplicar(b);
  };

  // arrastou uma peça (ou soltou fora): o chessground devolve só as peças
  const mudouNoTabuleiro = (placement: string) => aplicar(boardFromFen(placement));

  const digitarFen = (texto: string) => {
    setFenTexto(texto);
    const p = parseFen(texto);
    if (!p) {
      setFenErro(true);
      return;
    }
    setFenErro(false);
    setBoard(p.board);
    setTurn(p.turn);
    setCastling(p.castling);
  };

  const escolher = (p: Piece) =>
    setEscolha((atual) =>
      atual !== null && atual !== "apagar" && atual.role === p.role && atual.color === p.color ? null : p,
    );

  const marcada = (p: Piece) =>
    escolha !== null && escolha !== "apagar" && escolha.role === p.role && escolha.color === p.color;

  return (
    <div className="pos-editor">
      <Board
        fen={fen}
        orientation={orient}
        turnColor={turn}
        editor={{ onSquareClick: clicarCasa, onChange: mudouNoTabuleiro }}
      />

      <div className="pos-palette" style={{ marginTop: 8 }}>
        {CORES.map((color) =>
          ROLES.map((role) => {
            const p: Piece = { role, color };
            return (
              <button
                key={`${color}-${role}`}
                aria-label={NOME[role][color]}
                aria-pressed={marcada(p)}
                onClick={() => escolher(p)}
              >
                {GLIFO[color][role]}
              </button>
            );
          }),
        )}
      </div>

      <div className="row" style={{ marginTop: 8 }}>
        <button
          className="pos-apagar"
          aria-pressed={escolha === "apagar"}
          onClick={() => setEscolha((a) => (a === "apagar" ? null : "apagar"))}
        >
          Apagar
        </button>
        <button onClick={() => aplicar(boardFromFen(START_FEN), "white", TODO_ROQUE)}>Posição inicial</button>
        <button onClick={() => aplicar(new Map(), turn, SEM_ROQUE)}>Limpar</button>
        <button onClick={() => setOrient((o) => (o === "white" ? "black" : "white"))}>Inverter</button>
      </div>

      <div className="muted" style={{ marginTop: 6 }}>
        Escolha uma peça e clique nas casas. Arrastar move a peça; soltar fora do tabuleiro apaga.
      </div>

      <div className="row" style={{ marginTop: 10 }}>
        <label>
          <span className="muted">Lado a jogar </span>
          <select
            aria-label="Lado a jogar"
            value={turn}
            onChange={(e) => aplicar(board, e.target.value as Color)}
          >
            <option value="white">brancas</option>
            <option value="black">pretas</option>
          </select>
        </label>
      </div>

      <div className="row" style={{ marginTop: 8 }}>
        <span className="muted">Roques</span>
        {ROQUES.map(({ chave, rotulo, curto }) => (
          <label key={chave} className="pos-roque">
            <input
              type="checkbox"
              aria-label={rotulo}
              checked={roques[chave]}
              disabled={!pode[chave]}
              onChange={() => aplicar(board, turn, { ...castling, [chave]: !roques[chave] })}
            />
            <span className={pode[chave] ? undefined : "muted"}>{curto}</span>
          </label>
        ))}
      </div>

      <div style={{ marginTop: 10 }}>
        <div className="muted">FEN</div>
        <input
          aria-label="FEN"
          style={{ width: "100%" }}
          value={fenTexto ?? fen}
          onChange={(e) => digitarFen(e.target.value)}
        />
        {fenErro && <div className="msg bad">FEN inválido.</div>}
      </div>

      {erros.length > 0 && (
        <ul className="msg bad pos-erros">
          {erros.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}

      <div className="row" style={{ marginTop: 10 }}>
        <button className="primary" disabled={erros.length > 0 || fenErro} onClick={() => onUse(fen)}>
          {useLabel}
        </button>
        <button onClick={onCancel}>Cancelar</button>
      </div>
    </div>
  );
}
