import { Fragment, useMemo } from "react";
import { segmentar } from "./moveText";
import type { LanceDaLinha, Segmento } from "./moveText";

export interface TextoComLancesProps {
  texto: string;
  /** Posição de onde os lances do texto partem. */
  fen: string;
  /** Recebe a sequência da âncora até o lance clicado. */
  onPrevia: (linha: LanceDaLinha[]) => void;
  /** Mostra só os botões dos lances, sem a prosa (usado no editor, ao lado da caixa). */
  apenasLances?: boolean;
  /** Segmentos já prontos: evita quebrar o mesmo texto duas vezes por tecla. */
  segmentos?: Segmento[];
}

/**
 * Texto do autor com os lances virando links: clicar num deles pede a prévia da
 * linha até ali. A prosa sai como está (o `pre-wrap` preserva as quebras).
 */
export function TextoComLances({ texto, fen, onPrevia, apenasLances = false, segmentos }: TextoComLancesProps) {
  const segs = useMemo(() => segmentos ?? segmentar(texto, fen), [segmentos, texto, fen]);
  const lista = apenasLances ? segs.filter((s) => s.kind === "lance") : segs;
  return (
    <span className="texto-com-lances">
      {lista.map((s, i) =>
        s.kind === "texto" ? (
          <Fragment key={i}>{s.text}</Fragment>
        ) : (
          <Fragment key={i}>
            {apenasLances && i > 0 ? " " : null}
            <button
              type="button"
              className="lance-no-texto"
              title="mostrar no tabuleiro"
              onClick={() => onPrevia(s.linha)}
            >
              {s.text}
            </button>
          </Fragment>
        ),
      )}
    </span>
  );
}
