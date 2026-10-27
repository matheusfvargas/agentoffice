import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { TableKit } from "@tiptap/extension-table";
import { Placeholder } from "@tiptap/extensions";

import { iniciarFontes } from "./fontes.js";
import { Revisao, iniciarRevisao } from "./revisao.js";
import { criarPainelSugestoes } from "./sugestoes.js";
import "./estilo.css";

const editor = new Editor({
  element: document.getElementById("editor"),
  extensions: [
    StarterKit,
    TableKit.configure({ table: { resizable: false } }),
    Placeholder.configure({ placeholder: "Comece a escrever, ou digite / e peça algo ao agente…" }),
    Revisao,
  ],
  content: "<h1>Documento sem título</h1><p></p>",
  autofocus: "end",
});

const painel = criarPainelSugestoes(editor, document.getElementById("sugestoes"));
iniciarFontes();
iniciarRevisao(editor, {
  popover: document.getElementById("revisao-popover"),
  ativa: document.getElementById("revisao-ativa"),
  seletorIdioma: document.getElementById("revisao-idioma"),
  status: document.getElementById("revisao-status"),
});

editor.view.dom.addEventListener("keydown", (evento) => {
  if (evento.ctrlKey && evento.code === "Space") {
    evento.preventDefault();
    painel.abrir();
  }
});

const comandos = {
  h1: () => editor.chain().focus().toggleHeading({ level: 1 }).run(),
  h2: () => editor.chain().focus().toggleHeading({ level: 2 }).run(),
  negrito: () => editor.chain().focus().toggleBold().run(),
  italico: () => editor.chain().focus().toggleItalic().run(),
  lista: () => editor.chain().focus().toggleBulletList().run(),
  tabela: () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(),
  sugerir: () => painel.abrir(),
  exportar: exportarDocx,
};

document.getElementById("ferramentas").addEventListener("click", (evento) => {
  const botao = evento.target.closest("button[data-comando]");
  if (botao) comandos[botao.dataset.comando]();
});

async function exportarDocx() {
  const nome = document.getElementById("nome-documento").value.trim() || "documento";
  const resposta = await fetch("/api/exportar/docx", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ documento: editor.getJSON(), nome }),
  });
  if (!resposta.ok) {
    alert("Não foi possível exportar o documento.");
    return;
  }
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await resposta.blob());
  link.download = `${nome}.docx`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
