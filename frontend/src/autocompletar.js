// Autocompletar: depois de uma pausa na digitação, mostra em cinza, depois do cursor,
// como o agente continuaria o parágrafo. Tab aceita, Esc descarta, e continuar
// digitando as mesmas letras mantém o resto da sugestão.

import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

const chave = new PluginKey("autocompletar");
const ESPERA_MS = 800;
const MAX_CONTEXTO = 2000;

// O estado guarda a sugestão visível ({ pos, texto }) ou null. Qualquer mudança no
// texto ou no cursor que não venha do próprio autocompletar apaga a sugestão.
export const Autocompletar = Extension.create({
  name: "autocompletar",
  // Antes das listas, para o Tab aceitar a sugestão em vez de recuar o item.
  priority: 1000,
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: chave,
        state: {
          init: () => null,
          apply(transacao, sugestao) {
            const meta = transacao.getMeta(chave);
            if (meta !== undefined) return meta;
            return transacao.docChanged || transacao.selectionSet ? null : sugestao;
          },
        },
        props: {
          decorations(estado) {
            const sugestao = chave.getState(estado);
            if (!sugestao) return null;
            const fantasma = () => {
              const span = document.createElement("span");
              span.className = "autocompletar-fantasma";
              span.textContent = sugestao.texto;
              return span;
            };
            return DecorationSet.create(estado.doc, [Decoration.widget(sugestao.pos, fantasma, { side: 1 })]);
          },
          handleKeyDown(view, evento) {
            const sugestao = chave.getState(view.state);
            if (!sugestao) return false;
            if (evento.key === "Tab" && !evento.shiftKey) {
              view.dispatch(view.state.tr.insertText(sugestao.texto, sugestao.pos).setMeta(chave, null));
              return true;
            }
            if (evento.key === "Escape") {
              view.dispatch(view.state.tr.setMeta(chave, null));
              return true;
            }
            return false;
          },
          handleTextInput(view, de, ate, texto) {
            const sugestao = chave.getState(view.state);
            if (!sugestao || de !== ate || de !== sugestao.pos || !sugestao.texto.startsWith(texto)) return false;
            const resto = sugestao.texto.slice(texto.length);
            const transacao = view.state.tr.insertText(texto, de);
            view.dispatch(transacao.setMeta(chave, resto ? { pos: de + texto.length, texto: resto } : null));
            return true;
          },
        },
      }),
    ];
  },
});

export function iniciarAutocompletar(editor, { ativa, ocupado }) {
  let espera = null;
  let pedido = null;

  function cancelar() {
    clearTimeout(espera);
    pedido?.abort();
    pedido = null;
  }

  function agendar() {
    cancelar();
    if (ativa.checked) espera = setTimeout(sugerir, ESPERA_MS);
  }

  // Só sugere com o cursor parado no fim de um parágrafo com texto, fora do modo
  // "/instrução" e com o painel de sugestões fechado.
  function trechoAtual() {
    const { selection, doc } = editor.state;
    const { $head, empty } = selection;
    if (!empty || !$head.parent.isTextblock || $head.parentOffset !== $head.parent.content.size) return null;
    const texto = $head.parent.textContent;
    if (!texto.trim() || texto.startsWith("/")) return null;
    const contexto = doc.textBetween(0, $head.start(), "\n").slice(-MAX_CONTEXTO);
    return { pos: $head.pos, texto, contexto };
  }

  async function sugerir() {
    const trecho = trechoAtual();
    if (!trecho || ocupado()) return;
    const controle = new AbortController();
    pedido = controle;
    try {
      const resposta = await fetch("/api/completar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texto: trecho.texto, contexto: trecho.contexto }),
        signal: controle.signal,
      });
      if (!resposta.ok) return;
      const { sugestao } = await resposta.json();
      // O usuário pode ter digitado ou movido o cursor enquanto o modelo respondia.
      if (pedido !== controle || !sugestao || editor.state.selection.head !== trecho.pos || ocupado()) return;
      editor.view.dispatch(editor.state.tr.setMeta(chave, { pos: trecho.pos, texto: sugestao }));
    } catch (erro) {
      if (erro.name !== "AbortError") console.warn("Autocompletar indisponível:", erro);
    } finally {
      if (pedido === controle) pedido = null;
    }
  }

  editor.on("update", ({ transaction }) => {
    // Digitar as letras da sugestão já a mantém; não precisa pedir outra.
    if (chave.getState(editor.state)) cancelar();
    else if (transaction.docChanged) agendar();
  });
  editor.on("selectionUpdate", ({ transaction }) => {
    if (!transaction.docChanged) cancelar();
  });
  editor.on("blur", cancelar);
  ativa.addEventListener("change", () => {
    cancelar();
    editor.view.dispatch(editor.state.tr.setMeta(chave, null));
  });

  return {
    descartar() {
      cancelar();
      if (chave.getState(editor.state)) editor.view.dispatch(editor.state.tr.setMeta(chave, null));
    },
  };
}
