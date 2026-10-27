// Revisor de gramática: sublinha os erros que o LanguageTool encontra em cada
// parágrafo e, ao clicar no trecho sublinhado, mostra a explicação e as correções.

import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

const chave = new PluginKey("revisao");
const ESPERA_MS = 1200;

// Guarda os sublinhados no estado do editor e os acompanha enquanto o texto muda,
// até a próxima revisão substituí-los.
export const Revisao = Extension.create({
  name: "revisao",
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: chave,
        state: {
          init: () => DecorationSet.empty,
          apply(transacao, sublinhados) {
            return transacao.getMeta(chave) ?? sublinhados.map(transacao.mapping, transacao.doc);
          },
        },
        props: { decorations: (estado) => chave.getState(estado) },
      }),
    ];
  },
});

export function iniciarRevisao(editor, { popover, ativa, seletorIdioma, status }) {
  const cache = new Map(); // idioma + texto do parágrafo -> erros
  const ignorados = new Set(); // regra + trecho que o usuário mandou ignorar
  let espera = null;
  let rodada = 0;

  const chaveCache = (texto) => `${seletorIdioma.value}\u0000${texto}`;
  const chaveIgnorado = (erro, trecho) => `${erro.regra}\u0000${trecho}`;

  // Cada parágrafo (ou título, item de lista, célula) com a posição do primeiro
  // caractere. Elementos que não são texto (quebra de linha) viram "\n", que ocupa
  // a mesma 1 posição no documento; assim o deslocamento no texto bate com a posição.
  function blocos() {
    const lista = [];
    editor.state.doc.descendants((no, pos) => {
      if (!no.isTextblock) return true;
      let texto = "";
      no.forEach((filho) => (texto += filho.isText ? filho.text : "\n"));
      lista.push({ inicio: pos + 1, texto });
      return false;
    });
    return lista;
  }

  function agendar() {
    clearTimeout(espera);
    espera = setTimeout(revisarTudo, ESPERA_MS);
  }

  async function revisarTudo() {
    if (!ativa.checked) return;
    const minhaRodada = ++rodada;
    // Pedidos ao agente ("/insira ...") não são revisados.
    const textos = blocos()
      .map((b) => b.texto)
      .filter((t) => t.trim() && !t.startsWith("/") && !cache.has(chaveCache(t)));
    try {
      for (const texto of new Set(textos)) {
        const resposta = await fetch("/api/revisao", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ texto, idioma: seletorIdioma.value }),
        });
        const dados = await resposta.json();
        if (!resposta.ok) throw new Error(dados.detail || "Erro na revisão.");
        cache.set(chaveCache(texto), dados.erros);
        if (dados.idioma) mostrarStatus(`Idioma: ${dados.idioma}`);
        if (minhaRodada !== rodada) return; // uma rodada mais nova assumiu
      }
    } catch (erro) {
      mostrarStatus(erro.message, true);
      return;
    }
    if (minhaRodada === rodada) desenhar();
  }

  function desenhar() {
    const sublinhados = [];
    if (ativa.checked) {
      for (const { inicio, texto } of blocos()) {
        for (const erro of cache.get(chaveCache(texto)) ?? []) {
          const trecho = texto.slice(erro.inicio, erro.inicio + erro.tamanho);
          if (ignorados.has(chaveIgnorado(erro, trecho))) continue;
          const de = inicio + erro.inicio;
          sublinhados.push(
            Decoration.inline(de, de + erro.tamanho, { class: `erro-revisao erro-${erro.tipo}` }, { erro, trecho })
          );
        }
      }
    }
    const transacao = editor.state.tr
      .setMeta(chave, DecorationSet.create(editor.state.doc, sublinhados))
      .setMeta("addToHistory", false);
    editor.view.dispatch(transacao);
  }

  function abrirPopover(sublinhado) {
    const { erro, trecho } = sublinhado.spec;
    const sugestoes = erro.sugestoes
      .map((s, i) => `<button data-sugestao="${i}">${escapar(s) || "<em>remover</em>"}</button>`)
      .join("");
    popover.innerHTML = `
      <p class="mensagem">${escapar(erro.mensagem)}</p>
      <div class="opcoes-revisao">${sugestoes}</div>
      <button class="ignorar">Ignorar</button>`;
    popover.onclick = (evento) => {
      const botao = evento.target.closest("button");
      if (!botao) return;
      if (botao.classList.contains("ignorar")) {
        ignorados.add(chaveIgnorado(erro, trecho));
        desenhar();
      } else {
        corrigir(sublinhado, erro.sugestoes[Number(botao.dataset.sugestao)]);
      }
      fecharPopover();
    };
    const coords = editor.view.coordsAtPos(sublinhado.from);
    popover.style.top = `${coords.bottom + window.scrollY + 6}px`;
    popover.style.left = `${Math.max(16, Math.min(coords.left, window.innerWidth - 336))}px`;
    popover.hidden = false;
  }

  function corrigir(sublinhado, texto) {
    // insertText mantém a formatação (negrito, itálico) do trecho corrigido.
    const transacao = texto
      ? editor.state.tr.insertText(texto, sublinhado.from, sublinhado.to)
      : editor.state.tr.delete(sublinhado.from, sublinhado.to);
    // O sublinhado do trecho corrigido sai na hora, sem esperar a próxima revisão.
    const restantes = chave.getState(editor.state).remove([sublinhado]);
    editor.view.dispatch(transacao.setMeta(chave, restantes.map(transacao.mapping, transacao.doc)));
    editor.commands.focus();
  }

  function fecharPopover() {
    popover.hidden = true;
  }

  function mostrarStatus(texto, erro = false) {
    status.textContent = texto;
    status.classList.toggle("erro", erro);
  }

  editor.view.dom.addEventListener("click", (evento) => {
    const pos = editor.view.posAtCoords({ left: evento.clientX, top: evento.clientY })?.pos;
    if (pos == null) return;
    const [sublinhado] = chave.getState(editor.state).find(pos, pos);
    if (sublinhado) abrirPopover(sublinhado);
    else fecharPopover();
  });
  popover.addEventListener("mousedown", (evento) => evento.preventDefault()); // mantém o foco no editor
  document.addEventListener("keydown", (evento) => evento.key === "Escape" && fecharPopover());

  editor.on("update", () => {
    fecharPopover();
    agendar();
  });
  ativa.addEventListener("change", () => {
    if (ativa.checked) revisarTudo();
    else {
      mostrarStatus("");
      desenhar();
    }
  });
  seletorIdioma.addEventListener("change", revisarTudo);

  agendar();
}

function escapar(texto) {
  const div = document.createElement("div");
  div.textContent = texto;
  return div.innerHTML;
}
