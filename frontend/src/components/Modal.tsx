import type { ReactNode } from "react";

export interface ModalProps {
  open: boolean;
  title: string;
  onClose?: () => void;
  /** Modal largo: cabe um tabuleiro dentro (a montagem de posição usa). */
  wide?: boolean;
  children: ReactNode;
}

export function Modal({ open, title, onClose, wide, children }: ModalProps) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className={wide ? "modal card wide" : "modal card"}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0 }}>{title}</h3>
        {children}
      </div>
    </div>
  );
}
