import { test } from 'node:test';
import assert from 'node:assert/strict';
import { confirmarExclusao } from '../app/static/exclusao-registro.js';

const endpoint = '/avancos/507f1f77bcf86cd799439011';

for (const acao of ['cancelar', 'escape', 'confirmar', 'falha']) {
  test(`confirmação na interface: ${acao}`, async () => {
    let dialogo;
    globalThis.document = {
      body: { append() {} },
      createElement(tag) {
        const elemento = { tag, append(...filhos) { this.filhos = filhos; }, focus() {},
          close() {}, remove() { this.removido = true; },
          showModal() {
            queueMicrotask(() => {
              assert.match(this.filhos[0].textContent, /Excluir Concretagem/);
              assert.match(this.filhos[1].textContent, /versoes: 2/);
              if (acao === 'escape') this.oncancel({ preventDefault() {} });
              else this.filhos[acao === 'cancelar' ? 2 : 3].onclick();
            });
          } };
        if (tag === 'dialog') dialogo = elemento;
        return elemento;
      }
    };
    const chamadas = [];
    const requisitar = async (url, opcoes) => {
      chamadas.push({ url, opcoes });
      return { ok: acao !== 'falha' || !opcoes,
        json: async () => opcoes ? { mensagem: 'Limpeza pendente' } : {
          alvo: { id: endpoint.split('/').at(-1), nome: 'Concretagem', obra_id: 'obra', marco_id: 'marco' },
          perda: { publicacoes: 1, versoes: 2, midias: 3 }
        } };
    };
    if (acao === 'falha') await assert.rejects(confirmarExclusao(endpoint, requisitar), /Limpeza pendente/);
    else assert.equal(await confirmarExclusao(endpoint, requisitar), acao === 'confirmar');
    assert.equal(chamadas.length, ['confirmar', 'falha'].includes(acao) ? 2 : 1);
    assert.equal(chamadas[0].opcoes, undefined);
    if (chamadas.length === 2) {
      assert.equal(chamadas[1].opcoes.method, 'DELETE');
      assert.equal(JSON.parse(chamadas[1].opcoes.body).confirmar, true);
    }
    assert.equal(dialogo.removido, true);
  });
}
