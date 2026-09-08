import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ApiError } from "../src/api/client";
import { ErrorBox, errorList, errorMessage } from "../src/components/ErrorBox";

test("sem erro a caixa não aparece", () => {
  const { container } = render(<ErrorBox error={null} />);
  expect(container.firstChild).toBeNull();
});

test("erro comum vira uma linha só", () => {
  render(<ErrorBox error={new Error("rede fora")} />);
  expect(screen.getByRole("alert").textContent).toBe("rede fora");
  expect(errorList(new Error("rede fora"))).toBeNull();
  expect(errorMessage(new Error("rede fora"))).toBe("rede fora");
  expect(errorMessage("qualquer coisa")).toBe("Erro inesperado");
});

test("lista de mensagens do servidor vira uma por item", () => {
  const erro = new ApiError(422, "a; b", ["lance ilegal no nó n3: e2e5", "comentário longo demais"]);
  render(<ErrorBox error={erro} />);
  expect(screen.getByText("lance ilegal no nó n3: e2e5")).toBeTruthy();
  expect(screen.getByText("comentário longo demais")).toBeTruthy();
});

test("lista de erros do pydantic vira 'campo.sub: mensagem'", () => {
  const erro = new ApiError(422, "x", [
    { loc: ["body", "tree", "root"], msg: "Field required" },
    { loc: ["query", "limit"], msg: "Input should be less than or equal to 100" },
  ]);
  expect(errorList(erro)).toEqual([
    "body.tree.root: Field required",
    "query.limit: Input should be less than or equal to 100",
  ]);
  render(<ErrorBox error={erro} />);
  expect(screen.getByText("body.tree.root: Field required")).toBeTruthy();
});

test("item do pydantic sem loc (ou sem msg) ainda mostra o que tem", () => {
  expect(errorList(new ApiError(422, "x", [{ msg: "Value error" }]))).toEqual(["Value error"]);
  expect(errorList(new ApiError(422, "x", [{ loc: ["body"] }]))).toEqual(["body"]);
});
