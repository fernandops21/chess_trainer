import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { keys, useSettings, useStudies } from "../api/queries";
import type { ChapterOut, Tree } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { Modal } from "../components/Modal";

export interface SaveChapterModalProps {
  tree: Tree;
  onClose: () => void;
  /** Abre já em "novo estudo" (atalho da tela de análise). */
  newStudy?: boolean;
}

/**
 * Guarda a análise atual como capítulo: cria o estudo (se for novo), cria o
 * capítulo e manda a árvore no `PUT`. No fim abre o editor do capítulo.
 */
export function SaveChapterModal({ tree, onClose, newStudy = false }: SaveChapterModalProps) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: estudos } = useStudies();
  const { data: settings } = useSettings();
  const [destino, setDestino] = useState<"existente" | "novo">(newStudy ? "novo" : "existente");
  const [studyId, setStudyId] = useState("");
  const [titulo, setTitulo] = useState("");
  const [autor, setAutor] = useState<string | null>(null);
  const [nome, setNome] = useState("Capítulo 1");
  const [modo, setModo] = useState<ChapterOut["mode"]>("gamebook");
  const [erro, setErro] = useState<unknown>(null);
  const [salvando, setSalvando] = useState(false);

  // sem nenhum estudo ainda, só resta criar um; enquanto a lista não chega o
  // formulário fica no que o usuário escolheu (nada de pular de um para o outro)
  const semEstudos = estudos !== undefined && estudos.length === 0;
  const alvo = destino === "novo" || semEstudos ? "novo" : "existente";
  const escolhido = studyId || estudos?.[0]?.id || "";
  // o autor vem do nome configurado até o usuário digitar outro
  const nomeAutor = autor ?? settings?.chesscom_username ?? "";
  const nomeCapitulo = nome.trim() || "Capítulo 1";
  const impedido = salvando || (alvo === "novo" ? titulo.trim() === "" : escolhido === "");

  async function salvar() {
    setErro(null);
    setSalvando(true);
    try {
      const id =
        alvo === "novo"
          ? (await api.createStudy({ title: titulo.trim(), author: nomeAutor.trim() })).id
          : escolhido;
      const cap = await api.createChapter(id, {
        name: nomeCapitulo,
        fen: tree.fen,
        orientation: tree.orientation,
        mode: modo,
      });
      await api.saveChapter(id, cap.id, {
        name: nomeCapitulo,
        mode: modo,
        orientation: tree.orientation,
        tree,
      });
      void qc.invalidateQueries({ queryKey: keys.studies });
      setSalvando(false);
      onClose();
      navigate(`/estudos/${id}/capitulos/${cap.id}/editar`);
    } catch (e) {
      setErro(e);
      setSalvando(false);
    }
  }

  return (
    <Modal open title="Salvar como capítulo" onClose={onClose}>
      <div className="row" style={{ marginBottom: 10 }}>
        <input
          type="radio"
          id="destino-existente"
          name="destino"
          checked={alvo === "existente"}
          disabled={semEstudos}
          onChange={() => setDestino("existente")}
        />
        <label htmlFor="destino-existente">estudo existente</label>
        <input
          type="radio"
          id="destino-novo"
          name="destino"
          checked={alvo === "novo"}
          onChange={() => setDestino("novo")}
        />
        <label htmlFor="destino-novo">novo estudo</label>
      </div>

      {alvo === "existente" ? (
        <div style={{ marginBottom: 10 }}>
          <div className="muted">Estudo</div>
          <select
            aria-label="Estudo"
            style={{ width: "100%" }}
            value={escolhido}
            onChange={(e) => setStudyId(e.target.value)}
          >
            {estudos?.map((s) => (
              <option key={s.id} value={s.id}>{s.title}</option>
            ))}
          </select>
        </div>
      ) : (
        <div style={{ marginBottom: 10 }}>
          <div className="muted">Título do estudo</div>
          <input
            aria-label="Título do estudo"
            style={{ width: "100%" }}
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
          />
          <div className="muted" style={{ marginTop: 6 }}>Autor</div>
          <input
            aria-label="Autor"
            style={{ width: "100%" }}
            value={nomeAutor}
            onChange={(e) => setAutor(e.target.value)}
          />
        </div>
      )}

      <div style={{ marginBottom: 10 }}>
        <div className="muted">Nome do capítulo</div>
        <input
          aria-label="Nome do capítulo"
          style={{ width: "100%" }}
          value={nome}
          onChange={(e) => setNome(e.target.value)}
        />
      </div>

      <div style={{ marginBottom: 10 }}>
        <div className="muted">Modo</div>
        <select aria-label="Modo" value={modo} onChange={(e) => setModo(e.target.value as ChapterOut["mode"])}>
          <option value="gamebook">exercício</option>
          <option value="read">leitura</option>
        </select>
      </div>

      <ErrorBox error={erro} />
      <div className="row">
        <button className="primary" disabled={impedido} onClick={() => void salvar()}>Salvar</button>
        <button onClick={onClose}>Cancelar</button>
      </div>
    </Modal>
  );
}
