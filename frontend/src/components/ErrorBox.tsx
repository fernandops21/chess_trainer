import { ApiError } from "../api/client";

/**
 * Erros de validação do editor (422): o servidor manda `detail` como lista de
 * mensagens e o cliente serializa isso na mensagem do `ApiError`. Devolve as
 * mensagens quando é esse o caso, `null` nos erros comuns.
 */
export function errorList(error: unknown): string[] | null {
  if (!(error instanceof ApiError)) return null;
  const texto = error.message.trim();
  if (!texto.startsWith("[")) return null;
  try {
    const valor: unknown = JSON.parse(texto);
    if (Array.isArray(valor) && valor.length > 0 && valor.every((x) => typeof x === "string")) {
      return valor as string[];
    }
  } catch {
    /* mensagem comum que por acaso começa com "[" */
  }
  return null;
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
