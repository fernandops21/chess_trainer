import { useStatus } from "../api/queries";
import { JOB_LABEL } from "./JobCard";

const nf = new Intl.NumberFormat("pt-BR");

/** Uma linha embaixo do botão que dispara uma tarefa longa: diz que o clique funcionou, quanto
 *  já andou e como acabou. Só texto — a barra e o cancelar ficam no cartão "Tarefas" do início. */
export function JobStatusLine({ job }: { job: string }) {
  const { data: status } = useStatus();
  if (!status) return null;
  const j = status.job;
  if (j.state === "running" && j.job !== job) {
    return <div className="muted">Outra tarefa em andamento: {JOB_LABEL[j.job ?? ""] ?? j.job}</div>;
  }
  if (j.job !== job) return null;
  if (j.state === "running") {
    const quanto = j.total > 0 ? `${nf.format(j.done)} de ${nf.format(j.total)}` : j.message;
    return <div className="muted">{j.cancel_requested ? "Cancelando… " : "Em andamento: "}{quanto}</div>;
  }
  if (j.state === "error") return <div className="muted">Falhou: {j.error}</div>;
  return j.message ? <div className="muted">Última vez: {j.message}</div> : null;
}
