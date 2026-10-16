# Robô de Prazos: manual de instalação e uso

Sistema de gestão Débora Constantino · aba **Prazos & Intimações**

## 1. O que o robô faz

Todos os dias, às **06h30** (e também às **12h30** nos dias úteis), o robô:

1. lê no Gmail **deboraewenne@gmail.com** os e-mails de **oabsp@recortedigital.adv.br** e **intimacoes@info.aasp.org.br**;
2. separa cada publicação e identifica o processo, o cliente, o assunto e o juízo;
3. classifica o ato e define **o que deve ser feito** (contrarrazões, réplica, manifestação, recurso, julgamento virtual, ciência);
4. calcula a **publicação**, o **início do prazo**, a **quantidade de dias** e o **vencimento em dias úteis**, considerando feriados e a suspensão de 20/12 a 20/01;
5. atribui a **responsável** pelas regras cadastradas no sistema;
6. grava o prazo na aba **Prazos & Intimações** e cria a **tarefa** da colaboradora, que aparece em **Tarefas** e no **Calendário**. O prazo interno da tarefa fica 2 dias úteis antes do vencimento fatal;
7. cria um **evento no Google Agenda** no dia do vencimento, com a colaboradora convidada. Ela recebe o convite e lembretes 2 e 3 dias antes.

O robô **nunca apaga nem sobrescreve** o que a equipe editou. Se um prazo for reatribuído no sistema, a próxima execução atualiza o convite no Google Agenda. As publicações seguintes do mesmo processo continuam com a nova responsável.

### Regras de atribuição (padrão)

| Ordem | Regra | Responsável |
|---|---|---|
| 1 | Processo com final **0292** (Foro de Jacareí) | Rafaela |
| 2 | Assunto **Piso Salarial** | Amanda |
| 99 | Todos os demais | Dra. Débora |

As regras ficam no painel **🤖 Robô de prazos**, na aba Prazos & Intimações. Nesse painel também é possível incluir novas regras, por exemplo por número de processo específico, por assunto (como "Abono de Permanência") ou por trecho do texto. Para atribuir um único prazo a outra colaboradora, basta usar o seletor **👤** no próprio cartão do prazo.

### Prazos aplicados quando o despacho não informa o número de dias

| Ato | Prazo |
|---|---|
| Contrarrazões a recurso inominado (Juizado) | 10 dias úteis (Lei 9.099/95, art. 42, §2º) |
| Contrarrazões a apelação, recurso extraordinário e agravo | 15 dias úteis |
| Réplica "no prazo legal" | 15 dias úteis (CPC, arts. 350 e 351) |
| Intimação de acórdão | 5 dias úteis (embargos de declaração), com alerta para RE/REsp em 15 |
| Sentença em Juizado / Vara comum | 10 / 15 dias úteis para recurso |
| Despacho sem prazo expresso | 5 dias úteis (CPC, art. 218, §3º) |
| Julgamento virtual | último dia útil antes das 48 horas que antecedem a sessão |

Sempre que o robô presume um prazo, isso aparece em **Observações** no cartão do prazo. O robô é uma ferramenta de apoio: a advogada responsável deve conferir a publicação no e-SAJ antes de protocolar.

## 2. Instalação, feita uma única vez (cerca de 30 minutos)

### Passo 1. Enviar os arquivos ao GitHub

No repositório **advdeboraconstantino/gestao-escritorio**, envie pelo botão **Add file › Upload files**:

* `index.html`, que substitui o atual;
* a pasta `robo/` inteira;
* a pasta `.github/workflows/`, com o arquivo `robo-prazos.yml`;
* este manual.

> No navegador, a pasta `.github` pode ficar oculta. Se não aparecer para arrastar, crie o arquivo pelo próprio GitHub: **Add file › Create new file**, nome `.github/workflows/robo-prazos.yml`, e cole o conteúdo.

### Passo 2. Conta de serviço do Firebase (permite ao robô gravar no sistema)

1. Acesse **console.firebase.google.com** e abra o projeto **gestao-advdebora**.
2. Clique na engrenagem e vá em **Configurações do projeto › Contas de serviço**.
3. Clique em **Gerar nova chave privada** e salve o arquivo `.json`.
4. Abra o arquivo no Bloco de Notas e copie **todo** o conteúdo.

> Esse arquivo dá acesso total ao banco de dados. Não envie por WhatsApp ou e-mail, não suba no repositório e apague do computador depois do Passo 4.

### Passo 3. Autorizar a leitura do Gmail e a criação de eventos na Agenda

1. Acesse **console.cloud.google.com** com o projeto **gestao-advdebora** selecionado.
2. Ative as APIs **Gmail API** e **Google Calendar API**, em **APIs e serviços › Biblioteca**.
3. Configure a tela de consentimento em **APIs e serviços › Tela de consentimento OAuth**:
   * tipo **Externo**;
   * inclua deboraewenne@gmail.com como **usuário de teste**;
   * depois clique em **Publicar app**, para que a autorização não expire em 7 dias.
4. Em **Credenciais › Criar credenciais › ID do cliente OAuth**, escolha o tipo **App para computador** e baixe o arquivo como `credentials.json`.
5. No computador, com o Python instalado, abra o terminal dentro da pasta `robo` e rode:
   ```
   pip install google-auth-oauthlib
   python gerar_token_google.py
   ```
6. Faça o login com **deboraewenne@gmail.com** e autorize. O terminal mostrará três valores: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` e `GMAIL_REFRESH_TOKEN`.

### Passo 4. Cadastrar os segredos no GitHub

No repositório, vá em **Settings › Secrets and variables › Actions › New repository secret** e crie quatro segredos:

| Nome | Valor |
|---|---|
| `FIREBASE_SA_JSON` | todo o conteúdo do arquivo da conta de serviço (Passo 2) |
| `GMAIL_CLIENT_ID` | valor exibido no Passo 3 |
| `GMAIL_CLIENT_SECRET` | valor exibido no Passo 3 |
| `GMAIL_REFRESH_TOKEN` | valor exibido no Passo 3 |

Os segredos ficam criptografados e não aparecem no código, embora o repositório seja público.

### Passo 5. Conferir as colaboradoras e as regras no sistema

1. Na aba **Colaboradoras**, confirme que **Rafaela**, **Amanda** e **Débora** estão cadastradas com o **e-mail do Google** de cada uma. Esse e-mail é o que recebe o convite da Agenda.
2. Na aba **Prazos & Intimações**, abra o painel **🤖 Robô de prazos** e clique em **Gravar regras padrão no sistema**.

### Passo 6. Carga inicial desde 22/09/2026

1. No GitHub, vá em **Actions › Robô de Prazos › Run workflow**.
2. Primeiro, um teste: preencha `desde` = `2026-09-22`, marque **Somente simular** e clique em **Run**. Abra a execução e confira, no final do log, quantos e-mails e publicações foram lidos.
3. Depois, rode de novo com `desde` = `2026-09-22` e **sem** marcar a simulação. Os prazos e tarefas aparecerão no sistema em tempo real.

A partir daí, as execuções diárias acontecem sozinhas.

## 3. Uso no dia a dia

* **Prazos & Intimações:** a lista abre com os prazos ativos, do mais próximo ao mais distante. Há filtros por responsável, busca por processo ou cliente e uma opção "Somente ciência" para publicações sem prazo.
* **Cumprido:** ao clicar em "Marcar cumprido", a tarefa vinculada passa para "Concluída".
* **Reatribuir:** use o seletor 👤 no cartão. A tarefa muda de colaboradora na hora, e o convite da Agenda é ajustado na próxima execução do robô.
* **Prazo manual:** em "+ Nova Intimação / Prazo", a data final passa a ser calculada em **dias úteis**. Se a responsável não for escolhida, as regras automáticas definem quem assume, e a tarefa é criada automaticamente.
* **Feriados municipais ou suspensões do TJSP:** inclua as datas no painel do robô, por exemplo 28/10 (Dia do Servidor), se houver suspensão de expediente.

## 4. Segurança: ponto de atenção

O sistema acessa o Firestore direto do navegador, e não encontrei no código uma tela de login. Se as regras de segurança do Firestore estiverem abertas, qualquer pessoa com o endereço do site consegue ler e alterar os dados dos clientes.

**Recomendação:** ativar o **Firebase Authentication** com e-mail e senha para cada colaboradora e restringir as regras do Firestore a usuários autenticados. O robô continua funcionando normalmente, porque usa a conta de serviço.

## 5. Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| Execução falha com `invalid_grant` | autorização do Gmail expirou (app não publicado) | Publicar o app (Passo 3.3) e gerar novo token |
| Prazos sem responsável | nome da colaboradora diferente do cadastro | Ajustar a regra no painel, escolhendo a colaboradora na lista |
| Convite da Agenda não chega | e-mail da colaboradora vazio ou não Google | Corrigir o e-mail na aba Colaboradoras |
| Cliente "(identificar cliente)" | nome não encontrado na publicação | Editar o prazo; cadastrar o nº do processo no cliente melhora as próximas leituras |
