import { Link, useNavigate, useParams } from "react-router-dom";
import { useStudy } from "../api/queries";
import { ErrorBox } from "../components/ErrorBox";

export function StudyDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data, error, isLoading } = useStudy(id ?? null);
  return (
    <>
      <div className="row" style={{ alignItems: "baseline" }}>
        <h1 style={{ marginBottom: 0 }}>{data?.title ?? "Estudo"}</h1>
        <Link to="/estudos" className="muted">← todos os estudos</Link>
      </div>
      <ErrorBox error={error} />
      {isLoading && <p className="muted">Carregando…</p>}
      {data && (
        <>
          <div className="muted" style={{ marginBottom: 12 }}>
            {data.author || "sem autor"}
            {data.source_url && (
              <> · <a href={data.source_url} target="_blank" rel="noreferrer">ver no Lichess</a></>
            )}
          </div>
          <div className="card" style={{ padding: 0 }}>
            {data.chapters.map((c) => (
              <div key={c.id} style={{ padding: "10px 16px", borderBottom: "1px solid var(--line)" }}>
                <div className="row" style={{ alignItems: "baseline" }}>
                  <span className="muted">{c.order}.</span>
                  <b>{c.name}</b>
                  <span className="tag">{c.mode === "gamebook" ? "exercício" : "leitura (sem exercício)"}</span>
                  {!c.in_queue && <span className="tag">fora da repetição</span>}
                </div>
                {c.intro_comment && <div className="muted">{c.intro_comment}</div>}
                <div className="row" style={{ marginTop: 6 }}>
                  {c.puzzle_id && (
                    <button onClick={() => navigate(`/treinar?puzzle=${c.puzzle_id}`)}>Treinar este</button>
                  )}
                  {c.lichess_url && (
                    <a href={c.lichess_url} target="_blank" rel="noreferrer">ver no Lichess</a>
                  )}
                </div>
              </div>
            ))}
            {data.chapters.length === 0 && <p className="muted" style={{ padding: 16 }}>Estudo sem capítulos.</p>}
          </div>
        </>
      )}
    </>
  );
}
