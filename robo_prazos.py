#!/usr/bin/env python3
"""Robô de prazos — Débora Constantino Advocacia.

Lê no Gmail os e-mails do Recorte Digital OAB/SP e da AASP, extrai cada
publicação, identifica o que deve ser feito e o prazo, calcula o vencimento em
dias úteis, atribui a responsável pelas regras cadastradas no sistema e grava:
  * a coleção "prazos" (aba Prazos & Intimações);
  * a coleção "tarefas" (aba Tarefas / Calendário), uma por prazo;
  * um evento no Google Agenda no dia do vencimento, com a colaboradora convidada.

Uso:
  python robo_prazos.py                     # execução diária (últimos 4 dias)
  python robo_prazos.py --desde 2026-09-22  # carga inicial
  python robo_prazos.py --dry-run           # simula, não grava nada
  python robo_prazos.py --json-local arq.json [...]  # teste offline

Variáveis de ambiente (GitHub Secrets):
  FIREBASE_SA_JSON      conteúdo JSON da conta de serviço do Firebase
  GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN
  AGENDA_ATIVA          "1" para criar eventos no Google Agenda (padrão 1)
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calendario import Calendario  # noqa: E402
from classificador import classificar, norm  # noqa: E402
from publicacoes import parse_email  # noqa: E402

REMETENTES = ["oabsp@recortedigital.adv.br", "intimacoes@info.aasp.org.br"]
FUSO = timezone(timedelta(hours=-3))

REGRAS_PADRAO = [
    {"ordem": 1, "tipo": "final", "valor": "0292", "colaboradoraNome": "Rafaela", "ativo": True,
     "descricao": "Processos do Foro de Jacareí (final 0292)"},
    {"ordem": 2, "tipo": "assunto", "valor": "PISO SALARIAL", "colaboradoraNome": "Amanda", "ativo": True,
     "descricao": "Assunto Piso Salarial"},
    {"ordem": 99, "tipo": "padrao", "valor": "", "colaboradoraNome": "Débora", "ativo": True,
     "descricao": "Todos os demais processos"},
]


def hoje():
    return datetime.now(FUSO).date()


def chave(pub, cls):
    base = "|".join([pub["numero"], pub["disponibilizacao"].isoformat(), cls["tipoprazo"],
                     str(cls.get("dataSessao") or ""), norm(pub["texto"])[:160] if cls["tipoprazo"] != "Julgamento virtual" else ""])
    return hashlib.sha1(base.encode()).hexdigest()[:20]


# ---------------------------------------------------------------- Gmail
def gmail_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    cred = Credentials(None, refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
                       token_uri="https://oauth2.googleapis.com/token",
                       client_id=os.environ["GMAIL_CLIENT_ID"], client_secret=os.environ["GMAIL_CLIENT_SECRET"],
                       scopes=["https://www.googleapis.com/auth/gmail.readonly",
                               "https://www.googleapis.com/auth/calendar.events"])
    return cred


def _corpo(payload):
    textos, htmls = [], []

    def walk(p):
        mt = p.get("mimeType", "")
        data = p.get("body", {}).get("data")
        if data:
            s = base64.urlsafe_b64decode(data + "==").decode("utf-8", "replace")
            (textos if mt == "text/plain" else htmls if mt == "text/html" else textos).append(s)
        for c in p.get("parts", []) or []:
            walk(c)
    walk(payload)
    return "\n".join(textos), "\n".join(htmls)


def ler_emails(cred, desde: date):
    from googleapiclient.discovery import build
    svc = build("gmail", "v1", credentials=cred, cache_discovery=False)
    q = "from:(%s) after:%s" % (" OR ".join(REMETENTES), (desde - timedelta(days=1)).strftime("%Y/%m/%d"))
    ids, tok = [], None
    while True:
        r = svc.users().messages().list(userId="me", q=q, maxResults=100, pageToken=tok).execute()
        ids += [m["id"] for m in r.get("messages", [])]
        tok = r.get("nextPageToken")
        if not tok:
            break
    for mid in ids:
        m = svc.users().messages().get(userId="me", id=mid, format="full").execute()
        hdr = {h["name"].lower(): h["value"] for h in m["payload"].get("headers", [])}
        rem = hdr.get("from", "").lower()
        texto, html = _corpo(m["payload"])
        # OAB: o HTML preserva a tabela; AASP: o texto simples é mais limpo
        corpo = (html or texto) if "recortedigital" in rem else (texto or html)
        yield mid, rem, corpo


# ---------------------------------------------------------------- Firestore
class Banco:
    def __init__(self, dry=False):
        self.dry = dry
        self.db = None
        if os.environ.get("FIREBASE_SA_JSON"):
            import firebase_admin
            from firebase_admin import credentials, firestore
            info = json.loads(os.environ["FIREBASE_SA_JSON"])
            firebase_admin.initialize_app(credentials.Certificate(info))
            self.db = firestore.client()

    def todos(self, col):
        if not self.db:
            return []
        return [dict(d.to_dict(), id=d.id) for d in self.db.collection(col).stream()]

    def get(self, col, doc_id):
        if not self.db:
            return None
        d = self.db.collection(col).document(doc_id).get()
        return dict(d.to_dict(), id=d.id) if d.exists else None

    def set(self, col, doc_id, obj, merge=False):
        if self.dry or not self.db:
            return
        self.db.collection(col).document(doc_id).set(obj, merge=merge)


# ---------------------------------------------------------------- Atribuição
def localizar_colab(colabs, nome):
    n = norm(nome)
    for c in colabs:
        if n and n in norm(c.get("nome", "")):
            return c
    return {"id": "", "nome": nome, "email": ""}


def atribuir(pub, regras, colabs, fixos_processo):
    num = pub["numero"]
    if num in fixos_processo:  # reatribuição manual anterior para o mesmo processo
        return fixos_processo[num], "Mantida a responsável definida manualmente para este processo"
    alvo = norm(pub.get("assunto", "") + " " + pub.get("texto", "")[:500])
    for r in sorted([r for r in regras if r.get("ativo", True)], key=lambda r: r.get("ordem", 50)):
        tipo, valor = r.get("tipo"), norm(r.get("valor", ""))
        ok = (tipo == "processo" and re.sub(r"\D", "", valor) == re.sub(r"\D", "", num)) or \
             (tipo == "final" and num.endswith(valor.strip())) or \
             (tipo == "assunto" and valor and valor in alvo) or \
             (tipo == "texto" and valor and valor in norm(pub.get("texto", ""))) or \
             (tipo == "padrao")
        if ok:
            c = localizar_colab(colabs, r.get("colaboradoraNome", "")) if not r.get("colaboradoraId") else \
                next((x for x in colabs if x["id"] == r["colaboradoraId"]), {"id": r["colaboradoraId"], "nome": r.get("colaboradoraNome", ""), "email": ""})
            return c, "Regra: " + (r.get("descricao") or tipo + " " + r.get("valor", ""))
    return localizar_colab(colabs, "Débora"), "Regra padrão"


# ---------------------------------------------------------------- Agenda
def evento_agenda(cal_svc, prazo, existente_id=None):
    if not prazo.get("datafinal"):
        return None
    d = date.fromisoformat(prazo["datafinal"])
    titulo = "⚖️ %s · %s · %s" % (prazo["tipoprazo"], prazo["proc"], prazo.get("responsavelNome", ""))
    corpo = {
        "summary": titulo,
        "description": "%s\n\nCliente: %s\nPublicação: %s\nPrazo: %s dia(s) %s\nVencimento: %s\n\n%s\n\nGerado pelo Robô de Prazos." % (
            prazo.get("acao", ""), prazo.get("cliente", ""), prazo.get("pubdata", ""), prazo.get("dias", ""),
            prazo.get("contagem", ""), d.strftime("%d/%m/%Y"), prazo.get("textoIntegral", "")[:1500]),
        "start": {"date": d.isoformat()}, "end": {"date": (d + timedelta(days=1)).isoformat()},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 24 * 60 * 2},
                                                         {"method": "email", "minutes": 24 * 60 * 3}]},
        "extendedProperties": {"private": {"prazoId": prazo["id"]}},
    }
    if prazo.get("responsavelEmail") and "deboraewenne" not in prazo["responsavelEmail"]:
        corpo["attendees"] = [{"email": prazo["responsavelEmail"]}]
    if existente_id:
        return cal_svc.events().patch(calendarId="primary", eventId=existente_id, body=corpo,
                                      sendUpdates="all").execute()["id"]
    return cal_svc.events().insert(calendarId="primary", body=corpo, sendUpdates="all").execute()["id"]


# ---------------------------------------------------------------- Principal
def processar(pubs, banco, cal, cal_svc=None, log=print):
    regras = banco.todos("regras_atribuicao") or REGRAS_PADRAO
    colabs = banco.todos("colaboradoras")
    clientes = banco.todos("clientes")
    existentes = {p["id"]: p for p in banco.todos("prazos")}
    fixos = {}
    for p in existentes.values():
        if p.get("responsavelManual") and p.get("proc"):
            fixos[p["proc"]] = {"id": p.get("responsavelId", ""), "nome": p.get("responsavelNome", ""),
                                "email": p.get("responsavelEmail", "")}
    por_proc = {re.sub(r"\D", "", c.get("numproc", "")): c.get("nome", "") for c in clientes if c.get("numproc")}

    # OAB primeiro; AASP só entra se a mesma publicação não veio pela OAB
    pubs.sort(key=lambda p: 0 if p["fonte"].startswith("OAB") else 1)
    vistos_oab = {(p["numero"], p["disponibilizacao"]) for p in pubs if p["fonte"].startswith("OAB")}
    novos, ignorados, resumo = 0, 0, []
    ja = set()
    for pub in pubs:
        if pub["fonte"] == "AASP" and (pub["numero"], pub["disponibilizacao"]) in vistos_oab:
            continue
        cls = classificar(pub)
        k = chave(pub, cls)
        if k in ja:
            continue
        ja.add(k)
        pid = "pub_" + k
        publicacao = pub["publicacao"] or cal.publicacao(pub["disponibilizacao"])
        venc, inicio = None, None
        if cls.get("dataSessao"):
            # 48h antes do início (00:01) => último dia cheio para protocolar é sessão - 3 dias
            venc = cls["dataSessao"] - timedelta(days=3)
            while not cal.util(venc):
                venc -= timedelta(days=1)
        elif cls.get("dias"):
            inicio = cal.prox_util(publicacao)
            venc = cal.vencimento(publicacao, int(cls["dias"]), cls.get("uteis", True))
        resp, motivo = atribuir(pub, regras, colabs, fixos)
        cliente = por_proc.get(re.sub(r"\D", "", pub["numero"])) or pub.get("cliente") or "(identificar cliente)"
        obs = "; ".join(x for x in [cls.get("obs"), motivo,
                                    "Texto da AASP truncado: conferir íntegra no e-SAJ" if pub.get("truncado") else ""] if x)
        prazo = {
            "id": pid, "cliente": cliente, "proc": pub["numero"],
            "descr": cls["acao"], "pubdata": publicacao.isoformat(),
            "dias": str(cls["dias"]) if cls.get("dias") else "", "datafinal": venc.isoformat() if venc else "",
            "tipoprazo": cls["tipoprazo"], "obs": obs, "cumprido": False,
            "origem": "robo", "fonte": pub["fonte"], "emailId": pub.get("emailId", ""),
            "disponibilizacao": pub["disponibilizacao"].isoformat(),
            "inicioPrazo": inicio.isoformat() if inicio else "",
            "contagem": ("úteis" if cls.get("uteis", True) else "corridos") if cls.get("dias") else "",
            "acao": cls["acao"], "ciencia": bool(cls.get("ciencia")),
            "dataSessao": cls["dataSessao"].isoformat() if cls.get("dataSessao") else "",
            "orgao": pub.get("orgao", ""), "assunto": pub.get("assunto", ""), "classe": pub.get("classe", ""),
            "textoIntegral": pub["texto"],
            "responsavelId": resp.get("id", ""), "responsavelNome": resp.get("nome", ""),
            "responsavelEmail": resp.get("email", ""), "responsavelManual": False,
            "criadoEm": datetime.now(FUSO).isoformat(timespec="seconds"),
        }
        if pid in existentes:
            ignorados += 1
            continue
        novos += 1
        resumo.append(prazo)
        if prazo["datafinal"]:
            tid = "tar_" + k
            prazo["tarefaId"] = tid
            interno = cal.menos_uteis(venc, 2)
            if interno < hoje():
                interno = hoje() if venc >= hoje() else venc
            uteis_rest = cal.uteis_entre(hoje(), venc)
            prior = "Urgente" if uteis_rest <= 2 else "Alta" if uteis_rest <= 5 else "Média"
            tarefa = {
                "colaboradoraId": resp.get("id", ""), "colaboradoraNome": resp.get("nome", ""),
                "colaboradoraEmail": resp.get("email", ""),
                "titulo": "%s · %s" % (cls["tipoprazo"], pub["numero"]),
                "descricao": "%s\nCliente: %s\nVencimento fatal: %s (%s dia(s) %s)\n\n%s" % (
                    cls["acao"], cliente, venc.strftime("%d/%m/%Y"), prazo["dias"] or "-", prazo["contagem"],
                    pub["texto"][:800]),
                "prazo": interno.isoformat(), "hora": "", "prioridade": prior,
                "status": "Pendente", "obs": "Prazo interno (2 dias úteis antes do fatal). " + motivo,
                "vinculoTipo": "Prazo", "vinculoId": pid, "vinculoNome": "%s — %s" % (pub["numero"], cliente),
                "origem": "robo", "dataFatal": venc.isoformat(),
            }
            banco.set("tarefas", tid, tarefa)
            if cal_svc:
                try:
                    prazo["eventoAgendaId"] = evento_agenda(cal_svc, prazo)
                    prazo["eventoAgendaEmail"] = prazo["responsavelEmail"]
                except Exception as e:  # agenda nunca impede o registro do prazo
                    log("Agenda: falha em %s: %s" % (pid, e))
        banco.set("prazos", pid, prazo)
    return novos, ignorados, resumo


def sincronizar_agenda(banco, cal_svc, log=print):
    """Reflete no Google Agenda as reatribuições e mudanças de data feitas no sistema."""
    n = 0
    for p in banco.todos("prazos"):
        if p.get("origem") != "robo" or not p.get("datafinal") or p.get("cumprido"):
            continue
        if p.get("eventoAgendaId") and (p.get("eventoAgendaEmail", "") != p.get("responsavelEmail", "")
                                        or p.get("eventoAgendaData", p["datafinal"]) != p["datafinal"]):
            try:
                evento_agenda(cal_svc, p, p["eventoAgendaId"])
                banco.set("prazos", p["id"], {"eventoAgendaEmail": p.get("responsavelEmail", ""),
                                              "eventoAgendaData": p["datafinal"]}, merge=True)
                n += 1
            except Exception as e:
                log("Agenda: falha ao sincronizar %s: %s" % (p["id"], e))
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json-local", nargs="*")
    ap.add_argument("--saida")
    a = ap.parse_args()

    banco = Banco(dry=a.dry_run)
    cfg = banco.get("config", "feriados") or {}
    cal = Calendario(cfg.get("datas", []))
    desde = date.fromisoformat(a.desde) if a.desde else hoje() - timedelta(days=4)

    pubs, emails = [], 0
    if a.json_local:
        for f in a.json_local:
            d = json.load(open(f))
            emails += 1
            pubs += parse_email(d.get("sender", ""), d.get("plaintextBody", ""), d.get("id", ""))
        cred = None
    else:
        cred = gmail_service()
        for mid, rem, corpo in ler_emails(cred, desde):
            emails += 1
            pubs += parse_email(rem, corpo, mid)
    pubs = [p for p in pubs if p["disponibilizacao"] >= desde - timedelta(days=1)]

    cal_svc = None
    if cred and os.environ.get("AGENDA_ATIVA", "1") == "1" and not a.dry_run:
        from googleapiclient.discovery import build
        cal_svc = build("calendar", "v3", credentials=cred, cache_discovery=False)

    novos, ign, resumo = processar(pubs, banco, cal, cal_svc)
    sinc = sincronizar_agenda(banco, cal_svc) if cal_svc else 0
    exec_id = datetime.now(FUSO).strftime("%Y%m%d-%H%M%S")
    banco.set("robo_execucoes", exec_id, {
        "quando": datetime.now(FUSO).isoformat(timespec="seconds"), "desde": desde.isoformat(),
        "emailsLidos": emails, "publicacoes": len(pubs), "novosPrazos": novos, "jaExistentes": ign,
        "agendaSincronizados": sinc, "dryRun": a.dry_run})
    print("E-mails lidos: %d | publicações: %d | novos registros: %d | já existentes: %d | agenda sincronizada: %d"
          % (emails, len(pubs), novos, ign, sinc))
    if a.saida:
        json.dump(resumo, open(a.saida, "w"), ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
