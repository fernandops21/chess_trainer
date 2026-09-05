import { ApiError } from "../api/client";

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Erro inesperado";
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <div className="msg bad" role="alert">{errorMessage(error)}</div>;
}
