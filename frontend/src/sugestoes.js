// Painel que mostra as opções do agente logo abaixo do parágrafo atual.
//
// Dois modos, decididos pelo texto do parágrafo:
// - texto normal: as opções continuam o parágrafo e são inseridas no fim dele;
// - começa com "/": o resto é uma instrução e a opção escolhida substitui o parágrafo.

export function criarPainelSugestoes(editor, elemento) {
  let estado = null; // { de, ate, modo, opcoes, terminou, cancelar }

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

    estado?.cancelar.abort();
    const atual = {
      de,
      ate,
      modo: instrucao ? "substituir" : "continuar",
      opcoes: [],
      terminou: false,
      cancelar: new AbortController(),
    };
    estado = atual;
    posicionar(ate);
    mostrar('<p class="carregando">Pensando…</p>');

    try {
      const resposta = await fetch("/api/sugestoes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paragrafo: instrucao ? "" : texto, contexto, instrucao }),
        signal: atual.cancelar.signal,
      });
      if (!resposta.ok) {
        const dados = await resposta.json();
        throw new Error(dados.detail || "Erro ao gerar sugestões.");
      }
      for await (const evento of lerEventos(resposta)) {
        if (evento.erro) throw new Error(evento.erro);
        atual.opcoes = evento.opcoes;
        if (estado === atual) renderizarOpcoes();
      }
      atual.terminou = true;
      if (estado === atual) renderizarOpcoes();
    } catch (erro) {
      if (erro.name !== "AbortError" && estado === atual) {
        mostrar(`<p class="erro">${escapar(erro.message)}</p>`);
      }
    }
  }

  // Quantas opções já estão completas: durante o stream, a última ainda está sendo escrita.
  function prontas() {
    return estado.terminou ? estado.opcoes.length : Math.max(0, estado.opcoes.length - 1);
  }

  function renderizarOpcoes() {
    if (!estado.opcoes.length) {
      if (estado.terminou) mostrar('<p class="erro">O agente não trouxe sugestões. Tente de novo.</p>');
      return;
    }
    const itens = estado.opcoes
      .map((opcao, i) => {
        const escrevendo = i >= prontas();
        return `<li><button data-indice="${i}" ${escrevendo ? 'disabled class="escrevendo"' : ""}><kbd>${i + 1}</kbd> ${escapar(opcao)}</button></li>`;
      })
      .join("");
    const rodape = estado.terminou
      ? `<kbd>1</kbd>–<kbd>${estado.opcoes.length}</kbd> escolhe · <kbd>Esc</kbd> fecha`
      : "Escrevendo… · <kbd>Esc</kbd> fecha";
    mostrar(`<ol>${itens}</ol><p class="atalhos">${rodape}</p>`);
  }

  function aplicar(indice) {
    if (!estado || indice >= prontas()) return;
    const opcao = estado.opcoes[indice];
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
    estado?.cancelar.abort();
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
      // Com opções na tela, os números escolhem; uma opção ainda sendo escrita é ignorada.
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

// Lê a resposta NDJSON do backend, um objeto por linha, conforme chega.
async function* lerEventos(resposta) {
  const leitor = resposta.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await leitor.read();
    if (done) break;
    buffer += value;
    const linhas = buffer.split("\n");
    buffer = linhas.pop();
    for (const linha of linhas) if (linha.trim()) yield JSON.parse(linha);
  }
  if (buffer.trim()) yield JSON.parse(buffer);
}

function escapar(texto) {
  const div = document.createElement("div");
  div.textContent = texto;
  return div.innerHTML;
}
