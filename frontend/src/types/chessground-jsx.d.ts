import type { DetailedHTMLProps, HTMLAttributes } from "react";

// O `<piece>` é do chessground: os desenhos das peças são imagens de fundo de
// `.cg-wrap piece.<tipo>.<cor>` (arquivo `chessground.cburnett.css`). Quem
// escreve esse elemento à mão é a barra de material capturado (`MaterialBar`),
// para reaproveitar os sprites em vez de carregar um segundo conjunto.
declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      piece: DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement>;
    }
  }
}
