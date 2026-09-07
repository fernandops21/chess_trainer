import { useEffect, useRef } from "react";
import { MOVE_NAGS, nagLabel } from "./moveTree";

export interface NodeMenuProps {
  /** Posição do clique, em coordenadas da janela (o menu é `position: fixed`). */
  x: number;
  y: number;
  onPromote: () => void;
  onDelete: () => void;
  onNag: (nag: number) => void;
  onClose: () => void;
}

/** Menu do lance: promover, apagar e os NAGs de qualidade (!, ?, !!, ??, !?, ?!). */
export function NodeMenu({ x, y, onPromote, onDelete, onNag, onClose }: NodeMenuProps) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fora = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) onClose();
    };
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", tecla);
    };
  }, [onClose]);

  const acao = (fn: () => void) => () => {
    fn();
    onClose();
  };

  return (
    <div className="node-menu" role="menu" aria-label="Ações do lance" ref={box} style={{ left: x, top: y }}>
      <button type="button" role="menuitem" onClick={acao(onPromote)}>Promover a linha principal</button>
      <button type="button" role="menuitem" className="danger" onClick={acao(onDelete)}>Apagar daqui</button>
      <div className="row">
        {MOVE_NAGS.map((n) => (
          <button
            key={n}
            type="button"
            role="menuitem"
            aria-label={`marcar ${nagLabel(n)}`}
            onClick={acao(() => onNag(n))}
          >
            {nagLabel(n)}
          </button>
        ))}
      </div>
    </div>
  );
}
