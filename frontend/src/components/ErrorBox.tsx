import { ApiError, textoDoDetalhe } from "../api/client";

/**
 * Erros de validação (422): o servidor manda `detail` como lista — mensagens
 * prontas (o editor de capítulo) ou os objetos do pydantic — e o cliente guarda
 * essa lista no `ApiError`. Devolve uma linha por item, os do pydantic no
 * formato "campo.sub: mensagem"; `null` nos erros comuns.
 */
export function errorList(error: unknown): string[] | null {
  if (!(error instanceof ApiError)) return null;
  return error.details && error.details.length > 0 ? error.details.map(textoDoDetalhe) : null;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Erro inesperado";
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const lista = errorList(error);
  if (lista) {
    return (
      <div className="msg bad" role="alert">
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {lista.map((m, i) => (
            <li key={i}>{m}</li>
          ))}
        </ul>
      </div>
    );
  }
  return <div className="msg bad" role="alert">{errorMessage(error)}</div>;
}
