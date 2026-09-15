import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";
import { useCoachStatus, useSaveSettings, useSettings, useStartJob, useStatus, useTacticsStatus } from "../api/queries";
import type { Settings, SettingsIn } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { Modal } from "../components/Modal";
import { formatDate } from "../lib/format";

const nf = new Intl.NumberFormat("pt-BR");

const CATEGORIES = ["rapid", "daily", "classical", "blitz", "bullet"];
const RANGES: Record<string, [number, number]> = {
  analysis_depth: [6, 30], puzzle_depth: [6, 30], mistake_threshold_cp: [50, 1000], blunder_threshold_cp: [50, 1000],
  avoid_gap_cp: [50, 1000], unique_gap_cp: [50, 1000], new_per_day: [1, 100], leech_lapses: [2, 20],
  analysis_seconds: [1, 120], puzzle_search_seconds: [1, 120],
};

export function validate(s: Settings): string[] {
  const errs: string[] = [];
  for (const [k, [lo, hi]] of Object.entries(RANGES)) {
    const v = s[k as keyof Settings] as number;
    if (!Number.isInteger(v) || v < lo || v > hi) errs.push(`${k}: inteiro entre ${lo} e ${hi}`);
  }
  if (s.blunder_threshold_cp < s.mistake_threshold_cp) errs.push("blunder deve ser ≥ mistake");
  if (!s.chesscom_username.trim()) errs.push("informe o usuário do chess.com");
  if (s.tactics_window < 50) errs.push("janela de rating mínima é 50");
  if (s.tactics_rating < 400 || s.tactics_rating > 3200) errs.push("rating de táticas entre 400 e 3200");
  if (s.lichess_min_popularity < -100 || s.lichess_min_popularity > 100) errs.push("popularidade entre -100 e 100");
  if (s.lichess_min_plays < 0) errs.push("mínimo de partidas não pode ser negativo");
  return errs;
}

export function SettingsPage() {
  const { data, error } = useSettings();
  const { data: status } = useStatus();
  const { data: tactics } = useTacticsStatus();
  const { data: coach } = useCoachStatus();
  const save = useSaveSettings();
  const start = useStartJob();
  const [form, setForm] = useState<Settings | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [confirmAvoid, setConfirmAvoid] = useState(false);
  const [saved, setSaved] = useState(false);
  // Os segredos nunca voltam do servidor: cada um é um rascunho à parte do
  // formulário e só entra no PUT quando o usuário digita algo (vazio manteria o guardado).
  const [tokenDraft, setTokenDraft] = useState("");
  const [apiKeyDraft, setApiKeyDraft] = useState("");
  const [lfSecretDraft, setLfSecretDraft] = useState("");
  useEffect(() => { if (data && !form) setForm(data); }, [data, form]);
  if (error) return <ErrorBox error={error} />;
  if (!form) return <p className="muted">Carregando…</p>;
  const errs = validate(form);
  const salvar = (body: SettingsIn, opts: { soSegredo?: boolean } = {}) =>
    save.mutate(body, {
      onSuccess: (s) => {
        // "Remover" só mexe no segredo trocado: não descarta edições em andamento no resto do formulário
        setForm((f) =>
          opts.soSegredo && f
            ? { ...f, lichess_token_set: s.lichess_token_set, anthropic_api_key_set: s.anthropic_api_key_set, langfuse_secret_key_set: s.langfuse_secret_key_set }
            : s,
        );
        setTokenDraft("");
        setApiKeyDraft("");
        setLfSecretDraft("");
        if (!opts.soSegredo) {
          setSaved(true);
          setTimeout(() => setSaved(false), 2500);
        }
      },
    });
  const num = (k: keyof Settings) => (e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: Number(e.target.value) });
  const field = (label: string, k: keyof Settings) => (
    <label className="row" style={{ justifyContent: "space-between" }}>{label}<input type="number" value={form[k] as number} onChange={num(k)} style={{ width: 100 }} /></label>
  );
  return (
    <>
      <h1>Configurações</h1>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Chess.com</h3>
        <label className="row" style={{ justifyContent: "space-between" }}>usuário<input value={form.chesscom_username} onChange={(e) => setForm({ ...form, chesscom_username: e.target.value })} /></label>
        <div className="row" style={{ marginTop: 8 }}>
          {CATEGORIES.map((c) => (
            <label key={c}><input type="checkbox" checked={form.categories.includes(c)} onChange={(e) => setForm({ ...form, categories: e.target.checked ? [...form.categories, c] : form.categories.filter((x) => x !== c) })} /> {c}</label>
          ))}
        </div>
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Engine</h3>
        <label className="row" style={{ justifyContent: "space-between" }}>caminho do Stockfish<input value={form.stockfish_path} placeholder="vazio = procurar em engines/ ou no PATH" onChange={(e) => setForm({ ...form, stockfish_path: e.target.value })} style={{ flex: 1 }} /></label>
        <div className="muted">Estado atual: {status?.engine.available ? `encontrada em ${status.engine.path}` : "não encontrada"} (salve para testar um caminho novo)</div>
        {field("profundidade da análise", "analysis_depth")}
        {field("profundidade do puzzle", "puzzle_depth")}
        {field("tempo máximo por busca da análise (s)", "analysis_seconds")}
        {field("tempo máximo por busca do puzzle (s)", "puzzle_search_seconds")}
        <label className="row" style={{ justifyContent: "space-between" }}>
          Classificar lances na Análise (usa a engine)
          <input
            type="checkbox"
            checked={form.classify_moves}
            onChange={(e) => setForm({ ...form, classify_moves: e.target.checked })}
          />
        </label>
        <div className="muted">
          Cada lance do caminho aberto na Análise ganha um selo (melhor, imprecisão, erro…). Desligado, a engine
          só analisa a posição na tela.
        </div>
        <label className="row" style={{ justifyContent: "space-between" }}>
          Refutar o lance errado com a engine
          <input
            type="checkbox"
            checked={form.refute_wrong_moves}
            onChange={(e) => setForm({ ...form, refute_wrong_moves: e.target.checked })}
          />
        </label>
        <div className="muted">
          Ao errar, o lance entra no tabuleiro, a engine responde e o app mostra a queda de avaliação. Desligado,
          o lance é só recusado.
        </div>
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Erros e treino</h3>
        {field("limiar de mistake (cp)", "mistake_threshold_cp")}
        {field("limiar de blunder (cp)", "blunder_threshold_cp")}
        {field("gap mínimo do puzzle evitar (cp)", "avoid_gap_cp")}
        {field("lance único: distância mínima para a 2ª linha (cp)", "unique_gap_cp")}
        {field("puzzles novos por dia", "new_per_day")}
        <label className="row" style={{ justifyContent: "space-between" }}>
          Ordem dos novos
          <select value={form.new_order} aria-label="Ordem dos novos"
            onChange={(e) => setForm({ ...form, new_order: e.target.value === "recent" ? "recent" : "random" })}>
            <option value="random">aleatória</option>
            <option value="recent">mais recentes primeiro</option>
          </select>
        </label>
        {field("sanguessuga após N erros", "leech_lapses")}
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Banco de táticas (Lichess)</h3>
        <div>
          Estado: {tactics?.imported
            ? `${nf.format(tactics.count)} táticas · importado em ${tactics.imported_at ? formatDate(tactics.imported_at) : "data desconhecida"}`
            : "não importado"}
          {tactics && <span className="muted"> · {nf.format(tactics.attempts_total)} tentativas</span>}
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <button onClick={() => start.mutate({ kind: "import_lichess" })} disabled={status?.job.state === "running" || start.isPending}>
            Baixar e importar
          </button>
        </div>
        <div className="muted" style={{ marginTop: 6 }}>
          Download de ~300 MB de database.lichess.org; o arquivo fica em backend/data/ e a importação leva uns 5 minutos.
          Acompanhe o andamento no Painel; dá para cancelar (para no fim do lote atual).
        </div>
        {field("Rating de táticas (ajustado automaticamente)", "tactics_rating")}
        {field("Janela de rating (±)", "tactics_window")}
        {field("Mínimo de partidas jogadas", "lichess_min_plays")}
        {field("Popularidade mínima (−100 a 100)", "lichess_min_popularity")}
        <div className="muted">
          O rating é ajustado sozinho a cada tática resolvida; a janela define quão perto do seu rating as táticas são sorteadas.
          Mudar o filtro (partidas jogadas e popularidade) só afeta a próxima importação — o padrão (2000 e 90) guarda cerca de
          1 milhão de táticas.
        </div>
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Livro de aberturas (Lichess)</h3>
        <label className="row" style={{ justifyContent: "space-between" }}>
          Token do Lichess
          <input
            type="password"
            autoComplete="off"
            value={tokenDraft}
            placeholder={form.lichess_token_set ? "guardado; digite para trocar" : "cole o token aqui"}
            onChange={(e) => setTokenDraft(e.target.value)}
            style={{ flex: 1 }}
          />
        </label>
        <div className="muted">
          Necessário só para o livro de aberturas. Crie em{" "}
          <a href="https://lichess.org/account/oauth/token" target="_blank" rel="noreferrer">
            https://lichess.org/account/oauth/token
          </a>{" "}
          (sem permissões). Fica só no seu banco.
        </div>
        {form.lichess_token_set && (
          <div className="row" style={{ marginTop: 8 }}>
            <span className="msg ok">token configurado</span>
            <button onClick={() => salvar({ lichess_token: "" }, { soSegredo: true })} disabled={save.isPending}>Remover</button>
          </div>
        )}
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Treinador (IA)</h3>
        <label className="row" style={{ justifyContent: "space-between" }}>
          Chave da API da Anthropic
          <input type="password" autoComplete="off" value={apiKeyDraft} onChange={(e) => setApiKeyDraft(e.target.value)}
            placeholder={form.anthropic_api_key_set ? "guardada; digite para trocar" : "cole a chave aqui"} style={{ flex: 1 }} />
        </label>
        <div className="muted">
          Crie a chave no Console da Anthropic e defina lá um teto de gasto mensal. Cada explicação custa alguns centavos de dólar. Fica só no seu banco.
        </div>
        {form.anthropic_api_key_set && (
          <div className="row" style={{ marginTop: 8 }}>
            <span className="msg ok">chave configurada</span>
            <button onClick={() => salvar({ anthropic_api_key: "" }, { soSegredo: true })} disabled={save.isPending}>Remover chave</button>
          </div>
        )}
        <label className="row" style={{ justifyContent: "space-between" }}>
          Modelo
          <select aria-label="Modelo" value={form.coach_model} onChange={(e) => setForm({ ...form, coach_model: e.target.value as Settings["coach_model"] })}>
            <option value="claude-opus-5">Claude Opus 5 (melhor raciocínio)</option>
            <option value="claude-sonnet-5">Claude Sonnet 5 (mais barato)</option>
          </select>
        </label>
        <label className="row" style={{ justifyContent: "space-between" }}>
          Esforço
          <select aria-label="Esforço" value={form.coach_effort} onChange={(e) => setForm({ ...form, coach_effort: e.target.value as Settings["coach_effort"] })}>
            <option value="low">baixo</option><option value="medium">médio</option><option value="high">alto</option>
          </select>
        </label>
        <h4>Busca nos estudos</h4>
        <div className="muted">
          {coach?.embeddings_ready
            ? `${nf.format(coach.index_chunks)} trechos indexados (${coach.index_model}, ${coach.vector_backend})`
            : "modelo de embeddings ainda não baixado: o primeiro Recriar índice baixa cerca de 250 MB"}
          {coach && coach.index_stale > 0 ? ` · ${coach.index_stale} capítulos desatualizados` : ""}
        </div>
        <button onClick={() => start.mutate({ kind: "coach_reindex" })} disabled={status?.job.state === "running"}>Recriar índice</button>
        <h4>LangFuse (observabilidade)</h4>
        <label className="row" style={{ justifyContent: "space-between" }}>Host<input value={form.langfuse_host} placeholder="http://localhost:3000" onChange={(e) => setForm({ ...form, langfuse_host: e.target.value })} style={{ flex: 1 }} /></label>
        <label className="row" style={{ justifyContent: "space-between" }}>Chave pública do LangFuse<input value={form.langfuse_public_key} onChange={(e) => setForm({ ...form, langfuse_public_key: e.target.value })} style={{ flex: 1 }} /></label>
        <label className="row" style={{ justifyContent: "space-between" }}>
          Chave secreta do LangFuse
          <input type="password" autoComplete="off" value={lfSecretDraft} onChange={(e) => setLfSecretDraft(e.target.value)}
            placeholder={form.langfuse_secret_key_set ? "guardada; digite para trocar" : "cole a chave aqui"} style={{ flex: 1 }} />
        </label>
        <div className="muted">Opcional. Com o Docker Compose do projeto, o LangFuse roda em http://localhost:3000; crie um projeto lá e cole as chaves.</div>
      </div>
      {errs.length > 0 && <div className="msg bad">{errs.join(" · ")}</div>}
      <div className="row">
        <button className="primary" disabled={errs.length > 0 || save.isPending} onClick={() => {
          const { lichess_token_set: _a, anthropic_api_key_set: _b, langfuse_secret_key_set: _c, ...corpo } = form;
          const body: SettingsIn = { ...corpo };
          if (tokenDraft.trim()) body.lichess_token = tokenDraft.trim();
          if (apiKeyDraft.trim()) body.anthropic_api_key = apiKeyDraft.trim();
          if (lfSecretDraft.trim()) body.langfuse_secret_key = lfSecretDraft.trim();
          salvar(body);
        }}>Salvar</button>
        {saved && <span className="msg ok">Salvo.</span>}
        <ErrorBox error={save.error} />
      </div>
      <div className="card" style={{ marginTop: 20 }}>
        <h3 style={{ marginTop: 0 }}>Acesso pelo celular</h3>
        <div>Na mesma rede Wi-Fi, abra <b>{status?.local_url ?? "…"}</b>. Qualquer aparelho na rede consegue acessar; não há login.</div>
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0, color: "var(--bad)" }}>Perigo</h3>
        <button className="danger" onClick={() => setConfirm(true)} disabled={status?.job.state === "running"}>Recriar puzzles</button>
        <button className="danger" onClick={() => setConfirmAvoid(true)} disabled={status?.job.state === "running"}>Recriar só os evitar</button>
        <button onClick={() => start.mutate({ kind: "extend_puzzles" })} disabled={status?.job.state === "running"}>Estender exercícios</button>
        <div className="muted" style={{ marginTop: 6 }}>
          Alonga os exercícios existentes enquanto o lance for único, mantendo o histórico de revisão.
        </div>
        <ErrorBox error={start.error} />
      </div>
      <Modal open={confirm} title="Recriar todos os puzzles?" onClose={() => setConfirm(false)}>
        <p>Isso apaga <b>só os exercícios das suas partidas</b> e o histórico de treino deles (revisões, intervalos, sequência), e gera tudo de novo com os limiares atuais. As táticas guardadas do Lichess e os exercícios dos estudos ficam como estão. Não pode ser desfeito.</p>
        <div className="row"><button className="danger" onClick={() => { start.mutate({ kind: "regenerate" }); setConfirm(false); }}>Recriar</button><button onClick={() => setConfirm(false)}>Cancelar</button></div>
      </Modal>
      <Modal open={confirmAvoid} title="Recriar só os puzzles 'evitar'?" onClose={() => setConfirmAvoid(false)}>
        <p>Apaga e recria só os puzzles "evitar" das suas partidas (e o histórico de treino deles). Os "punir" e seu histórico ficam.</p>
        <div className="row"><button className="danger" onClick={() => { start.mutate({ kind: "regenerate", avoidOnly: true }); setConfirmAvoid(false); }}>Recriar</button><button onClick={() => setConfirmAvoid(false)}>Cancelar</button></div>
      </Modal>
    </>
  );
}
