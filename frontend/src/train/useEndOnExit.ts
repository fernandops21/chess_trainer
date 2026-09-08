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
 *
 * `sessaoEmCriacao` (opcional) devolve a promessa do `POST /api/sessions` ainda em
 * voo: sem ela, sair da tela antes da resposta deixaria a sessão aberta, porque
 * `sessionRef` ainda é `null` e o id só chega depois.
 */
export function useEndOnExit(
  sessionRef: RefObject<SessionOut | null>,
  endedRef: RefObject<boolean>,
  sessaoEmCriacao?: () => Promise<SessionOut | null> | null,
) {
  const sairRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // a função muda de identidade a cada render: o efeito de saída lê sempre a última
  const emCriacaoRef = useRef(sessaoEmCriacao);
  emCriacaoRef.current = sessaoEmCriacao;

  // O encerramento é agendado para o próximo tique porque, sob StrictMode, React
  // desmonta e remonta na hora: a remontagem cancela o agendamento e a sessão
  // continua de pé. Fora do StrictMode a desmontagem é definitiva e o tique roda.
  useEffect(() => {
    if (sairRef.current) { clearTimeout(sairRef.current); sairRef.current = null; }
    return () => {
      sairRef.current = setTimeout(() => {
        const encerrar = (s: SessionOut) => {
          if (endedRef.current) return;
          endedRef.current = true;
          // ninguém espera a resposta: a tela já saiu
          void api.endSession(s.id).catch(() => { /* sessão fica aberta, paciência */ });
        };
        if (endedRef.current) return;
        const s = sessionRef.current;
        if (s) { encerrar(s); return; }
        // a criação ainda está em voo: só dá para encerrar quando o id chegar
        void emCriacaoRef.current?.()?.then(
          (nova) => { if (nova) encerrar(nova); },
          () => { /* a sessão nem chegou a existir */ },
        );
      }, 0);
    };
  }, [sessionRef, endedRef]);

  // Fechar a aba não dá tempo de um fetch normal: `sendBeacon` sai junto com a página.
  // A rota é um POST sem corpo obrigatório, então o beacon vai vazio mesmo.
  useEffect(() => {
    const aoSair = (e: PageTransitionEvent) => {
      // `pagehide` também dispara quando a página só vai para o bfcache (Safari
      // móvel, aba em segundo plano): ela continua viva e pode voltar inteira
      if (e.persisted) return;
      const s = sessionRef.current;
      if (!s || endedRef.current || typeof navigator.sendBeacon !== "function") return;
      endedRef.current = true;
      navigator.sendBeacon(`/api/sessions/${s.id}/end`);
    };
    // de volta do bfcache a sessão continua de pé: destrava para encerrar mais tarde
    const aoVoltar = (e: PageTransitionEvent) => { if (e.persisted) endedRef.current = false; };
    window.addEventListener("pagehide", aoSair);
    window.addEventListener("pageshow", aoVoltar);
    return () => {
      window.removeEventListener("pagehide", aoSair);
      window.removeEventListener("pageshow", aoVoltar);
    };
  }, [sessionRef, endedRef]);
}
