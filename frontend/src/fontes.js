// Painel lateral de fontes: envia arquivos para o backend e lista o que já foi adicionado.

const entrada = document.getElementById("arquivo-fonte");
const lista = document.getElementById("lista-fontes");
const status = document.getElementById("status-fontes");

export async function iniciarFontes() {
  entrada.addEventListener("change", async () => {
    const arquivos = [...entrada.files];
    entrada.value = "";
    for (const arquivo of arquivos) await enviar(arquivo);
    await atualizarLista();
  });

  lista.addEventListener("click", async (evento) => {
    const botao = evento.target.closest("button[data-id]");
    if (!botao) return;
    await fetch(`/api/fontes/${botao.dataset.id}`, { method: "DELETE" });
    await atualizarLista();
  });

  await atualizarLista();
}

async function enviar(arquivo) {
  mostrarStatus(`Lendo ${arquivo.name}…`);
  const dados = new FormData();
  dados.append("arquivo", arquivo);
  try {
    const resposta = await fetch("/api/fontes", { method: "POST", body: dados });
    const corpo = await resposta.json();
    if (!resposta.ok) throw new Error(corpo.detail || "Não foi possível adicionar a fonte.");
    mostrarStatus(`${corpo.nome}: ${corpo.trechos} trechos indexados.`);
  } catch (erro) {
    mostrarStatus(erro.message, true);
  }
}

async function atualizarLista() {
  const resposta = await fetch("/api/fontes");
  const fontes = resposta.ok ? await resposta.json() : [];
  lista.replaceChildren(
    ...fontes.map((fonte) => {
      const item = document.createElement("li");
      const nome = document.createElement("span");
      nome.className = "nome";
      nome.textContent = fonte.nome;
      const detalhe = document.createElement("small");
      detalhe.textContent = `${fonte.trechos} trechos`;
      nome.append(detalhe);
      const remover = document.createElement("button");
      remover.dataset.id = fonte.id;
      remover.textContent = "Remover";
      remover.title = `Remover ${fonte.nome}`;
      item.append(nome, remover);
      return item;
    })
  );
}

function mostrarStatus(texto, erro = false) {
  status.textContent = texto;
  status.classList.toggle("erro", erro);
}
