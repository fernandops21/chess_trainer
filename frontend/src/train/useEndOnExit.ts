import { useEffect, useRef, type RefObject } from "react";
import { api } from "../api/client";
import type { SessionOut } from "../api/types";

/**
 * Encerra a sessão no servidor quando o usuário abandona a tela (trocou de menu,
 * voltou no navegador) ou fecha a aba. Sem isso a sessão fica aberta para sempre
 * e conta tempo que ninguém treinou.
 *
 * `endedRef` é a trava compartilhada com quem termina a sessão pelo caminho normal:
 * quem encerra primeiro marca, e a sessão nunca é encerrada duas vezes.
 */
export function useEndOnExit(sessionRef: RefObject<SessionOut | null>, endedRef: RefObject<boolean>) {
  const sairRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // O encerramento é agendado para o próximo tique porque, sob StrictMode, React
  // desmonta e remonta na hora: a remontagem cancela o agendamento e a sessão
  // continua de pé. Fora do StrictMode a desmontagem é definitiva e o tique roda.
  useEffect(() => {
    if (sairRef.current) { clearTimeout(sairRef.current); sairRef.current = null; }
    return () => {
      sairRef.current = setTimeout(() => {
        const s = sessionRef.current;
        if (!s || endedRef.current) return;
        endedRef.current = true;
        // ninguém espera a resposta: a tela já saiu
        void api.endSession(s.id).catch(() => { /* sessão fica aberta, paciência */ });
      }, 0);
    };
  }, [sessionRef, endedRef]);

  // Fechar a aba não dá tempo de um fetch normal: `sendBeacon` sai junto com a página.
  // A rota é um POST sem corpo obrigatório, então o beacon vai vazio mesmo.
  useEffect(() => {
    const aoSair = () => {
      const s = sessionRef.current;
      if (!s || endedRef.current || typeof navigator.sendBeacon !== "function") return;
      endedRef.current = true;
      navigator.sendBeacon(`/api/sessions/${s.id}/end`);
    };
    window.addEventListener("pagehide", aoSair);
    return () => window.removeEventListener("pagehide", aoSair);
  }, [sessionRef, endedRef]);
}
