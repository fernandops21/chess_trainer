import { useMemo } from "react";
import { TIPOS, materialCapturado, type Tipo } from "./material";
// os sprites das peças vêm daqui (`.cg-wrap piece.<tipo>.<cor>`); a importação é
// desta barra também, para não depender de o `Board` estar na tela
import "chessground/assets/chessground.cburnett.css";

/** Nome da peça no CSS do chessground. */
const CLASSE: Record<Tipo, string> = { p: "pawn", n: "knight", b: "bishop", r: "rook", q: "queen" };
/** Nome em português, no singular e no plural, para a leitura de tela. */
const NOME: Record<Tipo, [string, string]> = {
  p: ["peão", "peões"],
  n: ["cavalo", "cavalos"],
  b: ["bispo", "bispos"],
  r: ["torre", "torres"],
  q: ["dama", "damas"],
};
const LADO: Record<"white" | "black", string> = { white: "brancas", black: "pretas" };

export interface MaterialBarProps {
  fen: string;
  /** De quem é a barra: mostra o que ESTE lado capturou. */
  lado: "white" | "black";
  /** Com a barra de vantagem à esquerda do tabuleiro, a faixa anda o mesmo tanto. */
  deslocar?: boolean;
}

/**
 * Faixa com o material que um lado capturou, do jeito dos sites de xadrez: as
 * peças do adversário em miniatura e, para quem está na frente, o `+N` da
 * vantagem. Fica acima e abaixo do tabuleiro, uma barra por lado.
 *
 * Sem captura nenhuma a faixa continua desenhada (vazia): é o `min-height` do
 * CSS que impede o tabuleiro de saltar quando a primeira peça cai.
 */
export function MaterialBar({ fen, lado, deslocar = false }: MaterialBarProps) {
  const { capturadasPor, saldo } = useMemo(() => materialCapturado(fen), [fen]);
  const capturadas = capturadasPor[lado];
  // quem capturou branco vê peças pretas, e vice-versa
  const cor = lado === "white" ? "black" : "white";
  const vantagem = (lado === "white" ? saldo : -saldo) > 0 ? Math.abs(saldo) : 0;
  const grupos = TIPOS.filter((t) => capturadas[t] > 0);
  const lista = grupos
    .map((t) => `${capturadas[t]} ${NOME[t][capturadas[t] === 1 ? 0 : 1]}`)
    .join(", ");
  const rotulo = grupos.length > 0
    ? `${LADO[lado]} capturaram: ${lista}${vantagem > 0 ? `; +${vantagem}` : ""}`
    : vantagem > 0
      ? `${LADO[lado]}: +${vantagem} de material`
      : undefined;
  return (
    // barra vazia é enfeite de layout: sem rótulo, sai da leitura de tela
    <div
      className={`cg-wrap material-bar${deslocar ? " material-bar--deslocada" : ""}`}
      role={rotulo === undefined ? undefined : "img"}
      aria-label={rotulo}
      aria-hidden={rotulo === undefined ? true : undefined}
    >
      {grupos.map((t) => (
        <span className="material-grupo" key={t}>
          {Array.from({ length: capturadas[t] }, (_, i) => (
            <piece className={`${CLASSE[t]} ${cor}`} key={i} />
          ))}
        </span>
      ))}
      {vantagem > 0 && <span className="material-saldo">+{vantagem}</span>}
    </div>
  );
}
