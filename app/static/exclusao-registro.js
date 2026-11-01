/** Confirmação UC-18. `requisitar` deve ser o fetch autenticado da aplicação. */
export async function confirmarExclusao(endpoint, requisitar = fetch) {
  if (!/^\/((avancos)|(ocorrencias))\/[a-f0-9]{24}$/i.test(endpoint)) {
    throw new Error("Registro inválido");
  }
  const previa = await requisitar(`${endpoint}/exclusao`);
  if (!previa.ok) throw new Error("Não foi possível consultar a exclusão");
  const { alvo, perda } = await previa.json();
  const dialogo = document.createElement("dialog");
  const titulo = document.createElement("h2");
  titulo.textContent = `Excluir ${alvo.nome}?`;
  const aviso = document.createElement("p");
  aviso.textContent = `Exclusão definitiva do registro ${alvo.id}. Serão removidos: ` +
    Object.entries(perda).map(([nome, total]) => `${nome}: ${total}`).join(", ");
  const cancelar = document.createElement("button");
  cancelar.textContent = "Cancelar";
  const confirmar = document.createElement("button");
  confirmar.textContent = "Excluir definitivamente";
  dialogo.append(titulo, aviso, cancelar, confirmar);
  document.body.append(dialogo);
  try {
    const aceito = await new Promise(resolve => {
      cancelar.onclick = () => resolve(false);
      dialogo.oncancel = evento => { evento.preventDefault(); resolve(false); };
      confirmar.onclick = () => resolve(true);
      dialogo.showModal();
      cancelar.focus();
    });
    if (!aceito) return false;
    confirmar.disabled = cancelar.disabled = true;
    const resposta = await requisitar(endpoint, {
      method: "DELETE", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmar: true, obra_id: alvo.obra_id,
        ...(alvo.marco_id ? { marco_id: alvo.marco_id } : {}) })
    });
    if (!resposta.ok) {
      const erro = await resposta.json();
      throw new Error(erro.mensagem || "Exclusão não concluída");
    }
    return true;
  } finally {
    dialogo.close();
    dialogo.remove();
  }
}
