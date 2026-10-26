const form = document.getElementById("form-tarefa");
const campo = document.getElementById("tarefa");
const botao = form.querySelector("button");
const secao = document.getElementById("resultado");
const resposta = document.getElementById("resposta");
const lista = document.getElementById("arquivos");

form.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  botao.disabled = true;
  botao.textContent = "Gerando...";
  try {
    const r = await fetch("/api/tarefa", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tarefa: campo.value }),
    });
    const dados = await r.json();
    if (!r.ok) throw new Error(dados.detail || "Erro ao gerar.");
    resposta.textContent = dados.resposta;
    lista.replaceChildren(
      ...dados.arquivos.map((url) => {
        const item = document.createElement("li");
        const link = document.createElement("a");
        link.href = url;
        link.textContent = url.split("/").pop();
        item.append(link);
        return item;
      })
    );
  } catch (erro) {
    resposta.textContent = erro.message;
    lista.replaceChildren();
  } finally {
    secao.hidden = false;
    botao.disabled = false;
    botao.textContent = "Gerar";
  }
});
