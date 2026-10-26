// Painel que mostra as opções do agente logo abaixo do parágrafo atual.
//
// Dois modos, decididos pelo texto do parágrafo:
// - texto normal: as opções continuam o parágrafo e são inseridas no fim dele;
// - começa com "/": o resto é uma instrução e a opção escolhida substitui o parágrafo.

export function criarPainelSugestoes(editor, elemento) {
  let estado = null; // { de, ate, modo, opcoes }

  function blocoAtual() {
    const { $from } = editor.state.selection;
    const de = $from.start();
    const ate = $from.end();
    const texto = editor.state.doc.textBetween(de, ate, "\n");
    const contexto = editor.state.doc.textBetween(0, de, "\n");
    return { de, ate, texto, contexto };
  }

  async function abrir() {
    const { de, ate, texto, contexto } = blocoAtual();
    const instrucao = texto.startsWith("/") ? texto.slice(1).trim() : null;
    if (!texto.trim() || instrucao === "") return;

    estado = { de, ate, modo: instrucao ? "substituir" : "continuar", opcoes: [] };
    posicionar(ate);
    mostrar('<p class="carregando">Pensando…</p>');

    try {
      const resposta = await fetch("/api/sugestoes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paragrafo: instrucao ? "" : texto, contexto, instrucao }),
      });
      const dados = await resposta.json();
      if (!resposta.ok) throw new Error(dados.detail || "Erro ao gerar sugestões.");
      if (!estado) return; // o usuário fechou o painel enquanto esperava
      estado.opcoes = dados.opcoes;
      renderizarOpcoes();
    } catch (erro) {
      mostrar(`<p class="erro">${escapar(erro.message)}</p>`);
    }
  }

  function renderizarOpcoes() {
    if (!estado.opcoes.length) {
      mostrar('<p class="erro">O agente não trouxe sugestões. Tente de novo.</p>');
      return;
    }
    const itens = estado.opcoes
      .map((opcao, i) => `<li><button data-indice="${i}"><kbd>${i + 1}</kbd> ${escapar(opcao)}</button></li>`)
      .join("");
    mostrar(`<ol>${itens}</ol><p class="atalhos"><kbd>1</kbd>–<kbd>${estado.opcoes.length}</kbd> escolhe · <kbd>Esc</kbd> fecha</p>`);
  }

  function aplicar(indice) {
    const opcao = estado?.opcoes[indice];
    if (!opcao) return;
    const { de, ate, modo } = estado;
    const cadeia = editor.chain().focus();
    if (modo === "substituir") {
      cadeia.insertContentAt({ from: de, to: ate }, { type: "text", text: opcao });
    } else {
      const textoAtual = editor.state.doc.textBetween(de, ate);
      const separador = textoAtual.endsWith(" ") || /^[,.;:!?]/.test(opcao) ? "" : " ";
      cadeia.insertContentAt(ate, { type: "text", text: separador + opcao });
    }
    cadeia.run();
    fechar();
  }

  function fechar() {
    estado = null;
    elemento.hidden = true;
  }

  function mostrar(html) {
    elemento.innerHTML = html;
    elemento.hidden = false;
  }

  function posicionar(pos) {
    const coords = editor.view.coordsAtPos(pos);
    elemento.style.top = `${coords.bottom + window.scrollY + 8}px`;
    elemento.style.left = `${Math.max(16, Math.min(coords.left, window.innerWidth - 496))}px`;
  }

  elemento.addEventListener("mousedown", (evento) => evento.preventDefault()); // mantém o foco no editor
  elemento.addEventListener("click", (evento) => {
    const botao = evento.target.closest("button[data-indice]");
    if (botao) aplicar(Number(botao.dataset.indice));
  });

  editor.view.dom.addEventListener("keydown", (evento) => {
    if (!estado || elemento.hidden) return;
    if (evento.key === "Escape") {
      evento.preventDefault();
      fechar();
    } else if (/^[1-9]$/.test(evento.key) && estado.opcoes.length) {
      evento.preventDefault();
      aplicar(Number(evento.key) - 1);
    }
  });
  // Qualquer edição que mude o documento invalida as posições guardadas.
  editor.on("update", ({ transaction }) => {
    if (estado && transaction.docChanged) fechar();
  });

  return { abrir, fechar };
}

function escapar(texto) {
  const div = document.createElement("div");
  div.textContent = texto;
  return div.innerHTML;
}
