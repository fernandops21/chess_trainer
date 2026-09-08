import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AnalysisBoard } from "../analysis/AnalysisBoard";
import { emptyTree } from "../analysis/moveTree";
import type { Tree } from "../analysis/moveTree";
import { useChapter, useChapterActions } from "../api/queries";
import type { ChapterOut, Color } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";

const AVISO_SAIR = "Há alterações não salvas neste capítulo. Sair mesmo assim?";

const hora = (d: Date) => d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

/**
 * Editor de um capítulo: cabeçalho (nome, modo, orientação e enunciado) e o
 * mesmo tabuleiro de análise da tela `/analise`, aqui em modo de edição.
 *
 * A árvore vive nesta página: o tabuleiro devolve cada versão nova por
 * `onTreeChange` e o `PUT` manda essa árvore inteira. O enunciado é o
 * `intro` dela — a caixa do cabeçalho guarda um rascunho enquanto se digita
 * (trocar a árvore a cada tecla faria o tabuleiro voltar ao começo) e o
 * rascunho entra na árvore ao perder o foco ou na hora de salvar.
 */
export function ChapterEditorPage() {
  const { id = "", cid = "" } = useParams();
  const { data, error, isLoading } = useChapter(id, cid);
  const { save } = useChapterActions(id);

  const [tree, setTree] = useState<Tree | null>(null);
  const [nome, setNome] = useState("");
  const [modo, setModo] = useState<ChapterOut["mode"]>("gamebook");
  const [enunciado, setEnunciado] = useState("");
  const [dirty, setDirty] = useState(false);
  const [salvoEm, setSalvoEm] = useState<Date | null>(null);

  // Conta as edições do usuário. O `PUT` guarda o valor de antes de partir e,
  // na volta, só se dá por salvo se nada mudou no meio do caminho: o que foi
  // digitado com a requisição no ar continua pendente.
  const versao = useRef(0);
  const marcarSujo = useCallback(() => {
    versao.current += 1;
    setDirty(true);
  }, []);

  // Só o primeiro carregamento reinicia o formulário: depois de salvar, a
  // resposta do servidor volta pelo cache com o mesmo id e não pode desfazer
  // o que já está na tela.
  const carregado = useRef<string | null>(null);
  useEffect(() => {
    if (!data || carregado.current === data.id) return;
    carregado.current = data.id;
    const arvore = data.tree ?? emptyTree(data.fen, data.orientation);
    setTree(arvore);
    setNome(data.name);
    setModo(data.mode);
    setEnunciado(arvore.intro ?? "");
    versao.current = 0;
    setDirty(false);
    setSalvoEm(null);
  }, [data]);

  const aoMudarArvore = useCallback((t: Tree) => {
    setTree(t);
    setEnunciado(t.intro ?? "");
    marcarSujo();
  }, [marcarSujo]);

  // `save.mutate` é estável (TanStack Query); o resto entra nas dependências
  const { mutate: mandarSalvar, isPending: salvando } = save;
  const salvar = useCallback(() => {
    if (!tree || salvando) return;
    // o rascunho do enunciado ainda pode não ter entrado na árvore (só entra
    // ao perder o foco): salvar sempre manda a versão mais nova
    const arvore = tree.intro === enunciado ? tree : { ...tree, intro: enunciado };
    if (arvore !== tree) setTree(arvore);
    // trocar o enunciado aqui é parte do próprio salvamento, não uma edição nova
    const enviada = versao.current;
    mandarSalvar(
      { cid, body: { name: nome.trim() || "Capítulo", mode: modo, orientation: arvore.orientation, tree: arvore } },
      {
        onSuccess: (ch) => {
          // nada foi digitado com a requisição no ar: o formulário passa a mostrar
          // o que o servidor guardou (o nome aparado, a árvore normalizada). Se o
          // usuário editou no meio do caminho, o que está na tela é que vale.
          if (versao.current === enviada) {
            setDirty(false);
            const salva = ch.tree ?? emptyTree(ch.fen, ch.orientation);
            setNome(ch.name);
            setTree(salva);
            setEnunciado(salva.intro ?? "");
          }
          setSalvoEm(new Date());
        },
      },
    );
  }, [tree, nome, modo, enunciado, cid, salvando, mandarSalvar]);

  // Fechar a aba ou recarregar com alterações pendentes pede confirmação do
  // navegador; a navegação interna é barrada nos links desta tela.
  useEffect(() => {
    if (!dirty) return;
    const aoSair = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", aoSair);
    return () => window.removeEventListener("beforeunload", aoSair);
  }, [dirty]);

  const confirmarSaida = (e: { preventDefault: () => void }) => {
    if (dirty && !window.confirm(AVISO_SAIR)) e.preventDefault();
  };

  /** Muda a árvore da página; sem mudança de verdade, nada fica sujo. */
  const trocaArvore = (fn: (t: Tree) => Tree) => {
    if (!tree) return;
    const nova = fn(tree);
    if (nova === tree) return;
    setTree(nova);
    marcarSujo();
  };

  return (
    <>
      <div className="row" style={{ alignItems: "baseline" }}>
        <h1 style={{ marginBottom: 0 }}>Editar capítulo</h1>
        <Link to={`/estudos/${id}`} onClick={confirmarSaida}>Voltar ao estudo</Link>
        <Link to={`/estudos/${id}/capitulos/${cid}`} onClick={confirmarSaida}>Ver como leitura</Link>
      </div>

      <ErrorBox error={error} />
      <ErrorBox error={save.error} />
      {isLoading && <p className="muted">Carregando…</p>}

      {tree && (
        <>
          <div className="card">
            <div className="row">
              <label style={{ flex: "1 1 260px" }}>
                <div className="muted">Nome do capítulo</div>
                <input
                  aria-label="Nome do capítulo"
                  style={{ width: "100%" }}
                  value={nome}
                  onChange={(e) => { setNome(e.target.value); marcarSujo(); }}
                />
              </label>
              <label>
                <div className="muted">Modo</div>
                <select
                  aria-label="Modo"
                  value={modo}
                  onChange={(e) => { setModo(e.target.value as ChapterOut["mode"]); marcarSujo(); }}
                >
                  <option value="gamebook">exercício</option>
                  <option value="read">leitura</option>
                </select>
              </label>
              <label>
                <div className="muted">Orientação</div>
                <select
                  aria-label="Orientação"
                  value={tree.orientation}
                  onChange={(e) => {
                    const orientation = e.target.value as Color;
                    trocaArvore((t) => ({ ...t, orientation }));
                  }}
                >
                  <option value="white">brancas embaixo</option>
                  <option value="black">pretas embaixo</option>
                </select>
              </label>
            </div>
            <div style={{ marginTop: 10 }}>
              <div className="muted">Enunciado (comentário da posição inicial)</div>
              <textarea
                aria-label="Enunciado"
                style={{ width: "100%", minHeight: 60 }}
                value={enunciado}
                onChange={(e) => { setEnunciado(e.target.value); marcarSujo(); }}
                onBlur={() => trocaArvore((t) => (t.intro === enunciado ? t : { ...t, intro: enunciado }))}
              />
            </div>
            <div className="row" style={{ marginTop: 8, alignItems: "baseline" }}>
              <span className="muted">
                {salvando
                  ? "salvando…"
                  : dirty
                    ? "alterações não salvas"
                    : salvoEm
                      ? `salvo às ${hora(salvoEm)}`
                      : "sem alterações"}
              </span>
              <span className="muted">
                Ctrl+S ou o botão "Salvar" embaixo do tabuleiro; o modo "leitura" não gera exercício.
              </span>
            </div>
          </div>

          <AnalysisBoard
            editable
            engine={false}
            tree={tree}
            onTreeChange={aoMudarArvore}
            onSave={salvar}
            savedAt={salvoEm?.getTime()}
          />
        </>
      )}
    </>
  );
}
