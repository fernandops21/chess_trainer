import { useEffect, useRef, useState } from "react";
import { shortCode } from "../lib/format";

/** Etiqueta com o código curto do exercício; o clique copia o id inteiro.
 *
 * O que aparece é o prefixo (`#ff466803`), que já basta para abrir o exercício
 * pela URL ou para anotar num caderno; o que vai para a área de transferência é
 * o id completo, que serve em qualquer lugar e nunca fica ambíguo. */
export function CodeTag({ id }: { id: string }) {
  const [copiado, setCopiado] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const copiar = (e: { stopPropagation: () => void }) => {
    // a etiqueta às vezes fica dentro de um botão (a linha da revisão de erros):
    // copiar o código não deve abrir o que o clique na linha abriria
    e.stopPropagation();
    // fora de https (e no jsdom dos testes) não há área de transferência
    navigator.clipboard?.writeText(id).catch(() => undefined);
    setCopiado(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopiado(false), 1500);
  };
  return (
    <span className="tag copiavel" role="button" tabIndex={0} title="clique para copiar"
      onClick={copiar}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); copiar(e); } }}>
      {shortCode(id)}{copiado && <span className="muted"> copiado</span>}
    </span>
  );
}
